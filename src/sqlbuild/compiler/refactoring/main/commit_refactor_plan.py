"""Write a verified refactoring plan into the project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.refactoring._helpers.project.workspace import commit_changes
from sqlbuild.compiler.refactoring.models import RefactorPlan


def commit_refactor_plan(
    *, project_dir: Path, originals: dict[str, str], plan: RefactorPlan
) -> tuple[Path, ...]:
    """Write every change, restoring all files if any write fails, and return written paths."""

    return commit_changes(project_dir=project_dir, originals=originals, changes=plan.changes)
