"""Best-effort local execution history around parsed CLI dispatch."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.cli.commands._helpers.entry.dispatch import dispatch_cli_command
from sqlbuild.cli.commands._helpers.entry.history_diagnostics import (
    log_history_dispatch_failure,
    log_history_open_failure,
)
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.constants import DBT_INIT_COMMAND
from sqlbuild.cli.commands.models import CliEntrypointHandlers
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.execution_history import CanonicalLifecycleEvent
from sqlbuild.observability import EventDispatcher, create_lifecycle_event, dispatcher_scope
from sqlbuild.sqlite_history import SQLiteExecutionHistory


def dispatch_with_history(*, args: CliNamespace, handlers: CliEntrypointHandlers) -> int:
    """Dispatch once while retaining canonical invocation and nested run facts locally."""

    if _creates_project(args=args):
        return dispatch_cli_command(args=args, handlers=handlers)
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    try:
        history: SQLiteExecutionHistory = SQLiteExecutionHistory(project_dir=project_dir)
    except Exception as error:
        log_history_open_failure(error=error)
        return dispatch_cli_command(args=args, handlers=handlers)
    dispatcher: EventDispatcher = EventDispatcher(health_callback=log_history_dispatch_failure)
    _ = dispatcher.subscribe_lifecycle(
        subscriber=lambda event: _persist_event(history=history, event=event),
        accepts_opaque=True,
    )
    command: str = "unknown" if args.command is None else str(args.command)
    started: float = time.monotonic()
    try:
        with dispatcher_scope(dispatcher):
            dispatcher.publish_lifecycle(
                create_lifecycle_event(
                    event_type="invocation_started", payload={"command": command}
                )
            )
            try:
                exit_code: int = dispatch_cli_command(args=args, handlers=handlers)
            except BaseException as error:
                dispatcher.publish_lifecycle(
                    create_lifecycle_event(
                        event_type="invocation_failed",
                        payload={
                            "command": command,
                            "duration_ms": int((time.monotonic() - started) * 1000),
                            "error_type": type(error).__name__,
                        },
                    )
                )
                raise
            terminal_type: str = "invocation_completed" if exit_code == 0 else "invocation_failed"
            dispatcher.publish_lifecycle(
                create_lifecycle_event(
                    event_type=terminal_type,
                    payload={
                        "command": command,
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "exit_code": exit_code,
                    },
                )
            )
            return exit_code
    finally:
        try:
            history.close()
        except Exception:
            pass


def _persist_event(*, history: SQLiteExecutionHistory, event: CanonicalLifecycleEvent) -> None:
    _ = history.append_and_project((event,))


def _creates_project(*, args: CliNamespace) -> bool:
    return args.command in {CliCommand.INIT, CliCommand.PLAYGROUND} or (
        args.command == CliCommand.DBT and args.dbt_command == DBT_INIT_COMMAND
    )
