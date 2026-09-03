"""CLI lifecycle dispatcher, native progress, and exporter scope."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import Token
from pathlib import Path

from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.constants import (
    CSV_OUTPUT_FORMAT,
    DEBUG_COMMAND,
    JSON_OUTPUT_FORMAT,
    LINEAGE_COMMAND,
    QUERY_COMMAND,
)
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    terminal_event_index_scope,
)
from sqlbuild.cli.output.main._execution_event_output_active import execution_event_output_active
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.compiler.discovery.main.runtime_extensions import discover_runtime_extensions
from sqlbuild.compiler.discovery.models import DiscoveredEventExporter, DiscoveredProvider
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.observability import DispatchFailure, EventDispatcher, Unsubscribe, dispatcher_scope
from sqlbuild.presentation.main.supports_color import supports_color
from sqlbuild.runtime.event_exporting.classes.command_scope import EventExporterCommandScope
from sqlbuild.runtime.event_exporting.classes.dispatcher import EventExporterDispatcher
from sqlbuild.runtime.event_exporting.main.event_exporter_command_scope import (
    event_exporter_command_scope,
)
from sqlbuild.runtime.event_exporting.models import (
    EventExporterCounts,
    EventExporterFailure,
    EventExportSummary,
)

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cli.observability")


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
        or getattr(args, "event_output", None) is not None
        or execution_event_output_active()
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
    try:
        providers: tuple[DiscoveredProvider, ...]
        event_exporters: tuple[DiscoveredEventExporter, ...]
        providers, event_exporters = discover_runtime_extensions(project_dir=project_dir)
        if event_exporters:
            exporter_delivery: EventExporterDispatcher = EventExporterDispatcher(
                failure_callback=_log_exporter_failure,
                summary_callback=_log_exporter_summary,
            )
            exporter_scope = EventExporterCommandScope(dispatcher=exporter_delivery)
            exporter_scope.configure_extensions(
                project_dir=project_dir,
                providers=providers,
                event_exporters=event_exporters,
            )
            unsubscribe_exporters = dispatcher.subscribe_lifecycle(
                subscriber=exporter_delivery.enqueue,
                accepts_opaque=False,
            )
        with ExitStack() as stack:
            _ = stack.enter_context(dispatcher_scope(dispatcher))
            _ = stack.enter_context(terminal_event_index_scope(terminal_index))
            if exporter_scope is not None:
                _ = stack.enter_context(event_exporter_command_scope(exporter_scope))
            yield dispatcher
    finally:
        if unsubscribe_exporters is not None:
            _run_cleanup(action=unsubscribe_exporters, phase="event_exporter_unsubscribe")
        if exporter_scope is not None:
            _run_cleanup(action=exporter_scope.close, phase="event_exporter_shutdown")
        _run_cleanup(action=unsubscribe_terminal_index, phase="terminal_index_unsubscribe")
        _run_cleanup(action=unsubscribe_progress, phase="progress_unsubscribe")
        _run_cleanup(action=projector.close, phase="progress_close")
        _run_cleanup(
            action=lambda: projector.restore(projector_token),
            phase="progress_context_restore",
        )


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
