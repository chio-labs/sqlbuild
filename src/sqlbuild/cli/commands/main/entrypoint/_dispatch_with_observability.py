"""Canonical lifecycle publication around parsed CLI dispatch."""

from __future__ import annotations

import time
from pathlib import Path

from sqlbuild.cli.commands._helpers.entry.dispatch import dispatch_cli_command
from sqlbuild.cli.commands._helpers.entry.observability import cli_observability_scope
from sqlbuild.cli.commands.classes.cli_namespace import CliNamespace
from sqlbuild.cli.commands.constants import DBT_INIT_COMMAND
from sqlbuild.cli.commands.models import CliEntrypointHandlers
from sqlbuild.cli.commands.types import CliCommand
from sqlbuild.observability import create_lifecycle_event


def dispatch_with_observability(*, args: CliNamespace, handlers: CliEntrypointHandlers) -> int:
    """Dispatch once while publishing canonical invocation and nested run facts."""

    if _creates_project(args=args):
        return dispatch_cli_command(args=args, handlers=handlers)
    project_dir: Path = Path(args.project_dir) if args.project_dir is not None else Path.cwd()
    command: str = "unknown" if args.command is None else str(args.command)
    started: float = time.monotonic()
    with cli_observability_scope(
        args=args,
        project_dir=project_dir,
    ) as dispatcher:
        dispatcher.publish_lifecycle(
            create_lifecycle_event(event_type="invocation_started", payload={"command": command})
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


def _creates_project(*, args: CliNamespace) -> bool:
    return args.command in {CliCommand.INIT, CliCommand.PLAYGROUND} or (
        args.command == CliCommand.DBT and args.dbt_command == DBT_INIT_COMMAND
    )
