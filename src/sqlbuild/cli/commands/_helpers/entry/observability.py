"""CLI dispatcher, native progress, and local history subscription scope."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from contextvars import Token
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands._helpers.entry.history_diagnostics import (
    log_history_dispatch_failure,
    log_history_open_failure,
)
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.output.classes.terminal_event_index import (
    TerminalEventIndex,
    terminal_event_index_scope,
)
from sqlbuild.cli.output.main._execution_event_output_active import execution_event_output_active
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.compiler.discovery.main.runtime_extensions import discover_runtime_extensions
from sqlbuild.compiler.discovery.models import DiscoveredEventExporter, DiscoveredProvider
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.execution_history import CanonicalLifecycleEvent
from sqlbuild.observability import EventDispatcher, Unsubscribe, dispatcher_scope
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
from sqlbuild.sqlite_history import SQLiteExecutionHistory

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.cli.observability")


@contextmanager
def cli_observability_scope(
    *, args: CliNamespace, project_dir: Path, history_factory: Any = SQLiteExecutionHistory
) -> Iterator[EventDispatcher]:
    """Install coexisting history and native progress lifecycle subscribers."""

    dispatcher: EventDispatcher = EventDispatcher(health_callback=log_history_dispatch_failure)
    history: SQLiteExecutionHistory | None = _open_history(
        project_dir=project_dir, history_factory=history_factory
    )
    unsubscribe_history: Unsubscribe | None = (
        None
        if history is None
        else dispatcher.subscribe_lifecycle(
            subscriber=lambda event: _persist_event(history=history, event=event),
            accepts_opaque=True,
        )
    )
    terminal_index: TerminalEventIndex = TerminalEventIndex()
    unsubscribe_terminal_index: Unsubscribe = dispatcher.subscribe_lifecycle(
        subscriber=terminal_index.consume,
        accepts_opaque=False,
    )
    machine_output: bool = (
        args.json
        or getattr(args, "event_output", None) is not None
        or execution_event_output_active()
    )
    projector: NativeProgressProjector = NativeProgressProjector(
        stream=sys.stderr if machine_output or args.debug else sys.stdout,
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
        if unsubscribe_history is not None:
            _run_cleanup(action=unsubscribe_history, phase="history_unsubscribe")
        _run_cleanup(action=projector.close, phase="progress_close")
        _run_cleanup(
            action=lambda: projector.restore(projector_token),
            phase="progress_context_restore",
        )
        if history is not None:
            _run_cleanup(action=history.close, phase="history_close")


def _persist_event(*, history: SQLiteExecutionHistory, event: CanonicalLifecycleEvent) -> None:
    _ = history.append_and_project((event,))


def _open_history(*, project_dir: Path, history_factory: Any) -> SQLiteExecutionHistory | None:
    try:
        return history_factory(project_dir=project_dir)
    except Exception as error:
        log_history_open_failure(error=error)
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
