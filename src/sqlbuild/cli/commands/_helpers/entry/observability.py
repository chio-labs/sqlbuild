"""CLI lifecycle dispatcher, native progress, and exporter scope."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import Token
from functools import partial
from pathlib import Path

from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.constants import (
    CSV_OUTPUT_FORMAT,
    DEBUG_COMMAND,
    JSON_OUTPUT_FORMAT,
    LINEAGE_COMMAND,
    QUERY_COMMAND,
)
from sqlbuild.cli.commands.main.entrypoint._dispatch_with_output_capture import (
    configured_output_capture_scope,
)
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    terminal_event_index_scope,
)
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.compiler.discovery.main.runtime_extensions import discover_runtime_extensions
from sqlbuild.compiler.discovery.models import (
    DiscoveredCommandOutputSink,
    DiscoveredEventExporter,
    DiscoveredProvider,
    DiscoveredRuntimeExtensions,
)
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.constants import (
    DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS,
    INVOCATION_TERMINAL_EVENT_TYPES,
)
from sqlbuild.runtime.event_exporting.main.event_exporter_command_scope import (
    event_exporter_command_scope,
)
from sqlbuild.runtime.event_exporting.models import (
    EventExporterAccounting,
    EventExporterCounts,
    EventExporterFailure,
    EventExportSummary,
)
from sqlbuild.runtime.observability.classes.event_dispatcher import EventDispatcher
from sqlbuild.runtime.observability.main.current_execution_identity import (
    current_execution_identity,
)
from sqlbuild.runtime.observability.main.dispatcher_scope import dispatcher_scope
from sqlbuild.runtime.observability.models import (
    DispatchFailure,
    ExecutionIdentity,
    LifecycleEvent,
)
from sqlbuild.runtime.observability.types import Unsubscribe

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cli.observability")
_INVOCATION_COMPLETED_EVENT_TYPE: str = "invocation_completed"
_SHUTDOWN_TIMEOUT_SETTING: str = "sinks.lifecycle.shutdown_timeout"


@contextmanager
def cli_observability_scope(*, args: CliNamespace, project_dir: Path) -> Iterator[EventDispatcher]:
    """Install native progress, terminal indexing, and configured event exporters."""

    dispatcher: EventDispatcher = EventDispatcher(health_callback=_log_dispatch_failure)
    terminal_index: TerminalEventIndex = TerminalEventIndex()
    unsubscribe_terminal_index: Unsubscribe = dispatcher.subscribe_lifecycle(
        subscriber=terminal_index.consume,
        accepts_opaque=False,
    )
    machine_output: bool = (
        args.json
        or (args.command == LINEAGE_COMMAND and args.lineage_format == JSON_OUTPUT_FORMAT)
        or (
            args.command == QUERY_COMMAND
            and args.query_format in {CSV_OUTPUT_FORMAT, JSON_OUTPUT_FORMAT}
        )
    )
    projector: NativeProgressProjector = NativeProgressProjector(
        stream=sys.stderr
        if machine_output or args.debug or args.command == DEBUG_COMMAND
        else sys.stdout,
        use_color=not machine_output and not args.no_color and supports_color(),
    )
    unsubscribe_progress: Unsubscribe = dispatcher.subscribe_lifecycle(
        subscriber=projector.consume,
        accepts_opaque=False,
    )
    projector_token: Token[NativeProgressProjector | None] = projector.install()
    exporter_scope: EventExporterCommandScope | None = None
    unsubscribe_exporters: Unsubscribe | None = None
    unsubscribe_invocation_outcome: Unsubscribe | None = None
    invocation_outcome: _InvocationOutcome = _InvocationOutcome()
    final_export_summary: EventExportSummary | None = None
    try:
        extensions: DiscoveredRuntimeExtensions = (
            DiscoveredRuntimeExtensions()
            if args.command == LINEAGE_COMMAND
            else discover_runtime_extensions(project_dir=project_dir)
        )
        providers: tuple[DiscoveredProvider, ...] = extensions.providers
        event_exporters: tuple[DiscoveredEventExporter, ...] = extensions.event_exporters
        command_output_sinks: tuple[DiscoveredCommandOutputSink, ...] = (
            extensions.command_output_sinks
        )
        if event_exporters or command_output_sinks:
            exporter_delivery: EventExporterDispatcher = EventExporterDispatcher(
                shutdown_timeout_seconds=(
                    DEFAULT_EVENT_EXPORT_SHUTDOWN_TIMEOUT_SECONDS
                    if extensions.lifecycle_shutdown_timeout_seconds is None
                    else float(extensions.lifecycle_shutdown_timeout_seconds)
                ),
                failure_callback=_log_exporter_failure,
                summary_callback=_log_exporter_summary,
            )
            exporter_scope = EventExporterCommandScope(dispatcher=exporter_delivery)
            exporter_scope.configure_extensions(
                project_dir=project_dir,
                providers=providers,
                event_exporters=event_exporters,
                command_output_sinks=command_output_sinks,
            )
            unsubscribe_exporters = dispatcher.subscribe_lifecycle(
                subscriber=exporter_delivery.enqueue,
                accepts_opaque=False,
            )
            unsubscribe_invocation_outcome = dispatcher.subscribe_lifecycle(
                subscriber=invocation_outcome.consume,
                accepts_opaque=False,
            )
        with ExitStack() as stack:
            _ = stack.enter_context(dispatcher_scope(dispatcher))
            _ = stack.enter_context(terminal_event_index_scope(terminal_index))
            if exporter_scope is not None:
                _ = stack.enter_context(event_exporter_command_scope(exporter_scope))
                identity: ExecutionIdentity | None = current_execution_identity()
                if identity is not None and command_output_sinks:
                    _ = stack.enter_context(
                        configured_output_capture_scope(
                            exporter_scope=exporter_scope,
                            identity=identity,
                            failure_callback=_log_command_output_failure,
                        )
                    )
            yield dispatcher
    finally:
        if unsubscribe_exporters is not None:
            _run_cleanup(action=unsubscribe_exporters, phase="event_exporter_unsubscribe")
        if unsubscribe_invocation_outcome is not None:
            _run_cleanup(
                action=unsubscribe_invocation_outcome, phase="invocation_outcome_unsubscribe"
            )
        if exporter_scope is not None:
            final_export_summary = _close_exporter_scope(exporter_scope)
        _run_cleanup(action=unsubscribe_terminal_index, phase="terminal_index_unsubscribe")
        _run_cleanup(action=unsubscribe_progress, phase="progress_unsubscribe")
        _run_cleanup(action=projector.close, phase="progress_close")
        _run_cleanup(
            action=lambda: projector.restore(projector_token),
            phase="progress_context_restore",
        )
        if final_export_summary is not None:
            _run_cleanup(
                action=partial(
                    _warn_incomplete_export,
                    summary=final_export_summary,
                    command_succeeded=invocation_outcome.succeeded,
                ),
                phase="event_exporter_warning",
            )


def format_event_export_warning(
    *, summary: EventExportSummary, command_succeeded: bool
) -> str | None:
    """Return one stderr warning line when lifecycle events were dropped or failed."""

    if summary.dropped == 0 and summary.failed == 0:
        return None
    affected: tuple[EventExporterAccounting, ...] = tuple(
        exporter
        for exporter in summary.per_exporter
        if exporter.counts.dropped > 0 or exporter.counts.failed > 0
    )
    names: str = ", ".join(f"'{exporter.exporter_name}'" for exporter in affected)
    sink_label: str = "sink" if len(affected) == 1 else "sinks"
    unit: str = "events" if len(summary.per_exporter) == 1 else "event deliveries"
    prefix: str = (
        "Warning: command completed successfully, but lifecycle event export was incomplete"
        if command_succeeded
        else "Warning: lifecycle event export was incomplete"
    )
    return (
        f"{prefix}: {summary.dropped} of {summary.accepted} {unit} dropped, "
        f"{summary.failed} failed ({sink_label} {names}). "
        f"Increase {_SHUTDOWN_TIMEOUT_SETTING} or check sink health."
    )


class _InvocationOutcome:
    """Record whether the invocation published a successful terminal fact."""

    def __init__(self) -> None:
        self.succeeded: bool = False

    def consume(self, event: LifecycleEvent) -> None:
        if event.event_type in INVOCATION_TERMINAL_EVENT_TYPES:
            self.succeeded = event.event_type == _INVOCATION_COMPLETED_EVENT_TYPE


def _warn_incomplete_export(*, summary: EventExportSummary, command_succeeded: bool) -> None:
    message: str | None = format_event_export_warning(
        summary=summary, command_succeeded=command_succeeded
    )
    if message is not None:
        print(message, file=sys.stderr, flush=True)


def _close_exporter_scope(scope: EventExporterCommandScope) -> EventExportSummary | None:
    try:
        return scope.close()
    except BaseException as error:
        _report_cleanup_failure(error=error, phase="event_exporter_shutdown")
        return None


def _run_cleanup(*, action: Callable[[], object], phase: str) -> None:
    try:
        _ = action()
    except BaseException as error:
        _report_cleanup_failure(error=error, phase=phase)


def _report_cleanup_failure(*, error: BaseException, phase: str) -> None:
    try:
        log_debug_event(
            logger=_LOGGER,
            message="CLI observability cleanup failed",
            error_type=type(error).__name__,
            phase=phase,
        )
    except BaseException:
        pass


def _log_dispatch_failure(failure: DispatchFailure) -> None:
    log_debug_event(
        logger=_LOGGER,
        message="Lifecycle event subscriber failed",
        error_type=failure.error_type,
        channel=failure.channel,
        subscriber=failure.subscriber,
    )


def _log_exporter_failure(failure: EventExporterFailure) -> None:
    log_debug_event(
        logger=_LOGGER,
        message="Event exporter delivery failed",
        exporter_name=failure.exporter_name,
        error_type=failure.error_type,
        event_kind=failure.event_kind,
        event_severity=failure.event_severity,
    )


def _log_command_output_failure(error: BaseException) -> None:
    log_debug_event(
        logger=_LOGGER,
        message="Command-output sink delivery failed",
        error_type=type(error).__name__,
    )


def _log_exporter_summary(summary: EventExportSummary) -> None:
    log_debug_event(
        logger=_LOGGER,
        message="Event exporter delivery summary",
        accepted=summary.accepted,
        filtered=summary.filtered,
        delivered=summary.delivered,
        failed=summary.failed,
        dropped=summary.dropped,
        queue_depth=summary.queue_depth,
        queue_capacity=summary.queue_capacity,
        flush_complete=summary.flush_complete,
    )
    for exporter in summary.per_exporter:
        counts: EventExporterCounts = exporter.counts
        log_debug_event(
            logger=_LOGGER,
            message="Event exporter accounting",
            exporter_name=exporter.exporter_name,
            accepted=counts.accepted,
            filtered=counts.filtered,
            delivered=counts.delivered,
            failed=counts.failed,
            dropped=counts.dropped,
            queue_depth=summary.queue_depth,
            queue_capacity=summary.queue_capacity,
            flush_complete=summary.flush_complete,
        )
