"""CLI state command entry point."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.versioned.state.main.lifecycle import run_state_lifecycle
from sqlbuild.versioned.state.types import StateCommand


def run_state(
    project_dir: Path | None,
    state_command: str,
    backup_id: str | None = None,
    auto_approve: bool = False,
) -> int:
    """Execute a versioned state lifecycle command."""

    return run_state_lifecycle(
        project_dir=project_dir,
        command=StateCommand(state_command),
        backup_id=backup_id,
        auto_approve=auto_approve,
    )
