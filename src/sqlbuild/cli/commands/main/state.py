"""CLI state command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.main.helpers.state.checkpoints import run_state_checkpoints
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
) -> int:
    """Execute a virtual state lifecycle command."""

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
