"""CLI dispatcher, native progress, and local history subscription scope."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import Token
from pathlib import Path
from typing import Any

from sqlbuild.cli.commands._helpers.entry.history_diagnostics import (
    log_history_dispatch_failure,
    log_history_open_failure,
)
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.progress.classes.native_progress_projector import NativeProgressProjector
from sqlbuild.diagnostics.main.log_debug_event import log_debug_event
from sqlbuild.execution_history import CanonicalLifecycleEvent
from sqlbuild.observability import EventDispatcher, Unsubscribe, dispatcher_scope
from sqlbuild.presentation.main.supports_color import supports_color
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
    machine_output: bool = args.json
    projector: NativeProgressProjector = NativeProgressProjector(
        stream=sys.stderr if machine_output or args.debug else sys.stdout,
        use_color=not machine_output and not args.no_color and supports_color(),
    )
    unsubscribe_progress: Unsubscribe = dispatcher.subscribe_lifecycle(
        subscriber=projector.consume,
        accepts_opaque=False,
    )
    projector_token: Token[NativeProgressProjector | None] = projector.install()
    try:
        with dispatcher_scope(dispatcher):
            yield dispatcher
    finally:
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
