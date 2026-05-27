"""CLI state command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.state.checkpoints import run_state_checkpoints
from sqlbuild.cli.commands.main.helpers.state.interactive_operation import (
    run_interactive_state_operation,
)
from sqlbuild.virtual.state.main.adopt import run_state_adopt
from sqlbuild.virtual.state.main.detach import run_state_detach
from sqlbuild.virtual.state.main.lifecycle import run_state_lifecycle
from sqlbuild.virtual.state.types import StateCommand


def run_state(
    project_dir: Path | None,
    state_command: str,
    backup_id: str | None = None,
    auto_approve: bool = False,
    no_color: bool = False,
    checkpoint_command: str | None = None,
    checkpoint_id: str | None = None,
    virtual_environment: str | None = None,
    allow_copy: bool = False,
) -> int:
    """Execute a virtual state lifecycle command."""

    if state_command == StateCommand.ADOPT.value:
        return _run_state_adopt_command(
            project_dir=project_dir,
            auto_approve=auto_approve,
            allow_copy=allow_copy,
        )
    if state_command == StateCommand.DETACH.value:
        return _run_state_detach_command(
            project_dir=project_dir,
            auto_approve=auto_approve,
            allow_copy=allow_copy,
        )
    if state_command == "checkpoints":
        return run_state_checkpoints(
            project_dir=project_dir,
            command=checkpoint_command,
            checkpoint_id=checkpoint_id,
            virtual_environment_name=virtual_environment,
            no_color=no_color,
        )
    return run_state_lifecycle(
        project_dir=project_dir,
        command=StateCommand(state_command),
        backup_id=backup_id,
        auto_approve=auto_approve,
        no_color=no_color,
    )


def _run_state_adopt_command(
    *,
    project_dir: Path | None,
    auto_approve: bool,
    allow_copy: bool,
) -> int:
    return run_interactive_state_operation(
        project_dir=project_dir,
        state_command=StateCommand.ADOPT,
        operation_runner=run_state_adopt,
        auto_approve=auto_approve,
        allow_copy=allow_copy,
    )


def _run_state_detach_command(
    *,
    project_dir: Path | None,
    auto_approve: bool,
    allow_copy: bool,
) -> int:
    return run_interactive_state_operation(
        project_dir=project_dir,
        state_command=StateCommand.DETACH,
        operation_runner=run_state_detach,
        auto_approve=auto_approve,
        allow_copy=allow_copy,
    )
