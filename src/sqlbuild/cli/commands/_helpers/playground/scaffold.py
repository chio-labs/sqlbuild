"""Playground target resolution and project scaffolding phases."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.playground.copy import create_playground_project
from sqlbuild.cli.commands._helpers.skills.update import update_sqlbuild_skills
from sqlbuild.cli.commands.models import (
    PlaygroundCommandRequest,
    PlaygroundTarget,
)
from sqlbuild.cli.commands.types import PlaygroundTemplate


def resolve_playground_target(*, request: PlaygroundCommandRequest) -> PlaygroundTarget:
    """Resolve the playground destination directory and template."""

    base_dir: Path = request.project_dir if request.project_dir is not None else Path.cwd()
    target_dir: Path = Path(request.target_path)
    if not target_dir.is_absolute():
        target_dir = base_dir / target_dir
    return PlaygroundTarget(
        target_dir=target_dir,
        template=PlaygroundTemplate(request.template),
    )


def write_playground_project(*, target: PlaygroundTarget) -> None:
    """Create the playground project files and refresh bundled skills."""

    create_playground_project(target_dir=target.target_dir, template=target.template.value)
    _ = update_sqlbuild_skills(project_dir=target.target_dir)
