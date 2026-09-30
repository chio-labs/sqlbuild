"""Stage a refactoring plan in a scratch copy of the project."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.refactoring._helpers.project.workspace import (
    copy_project_inputs,
    read_originals,
    write_staged_changes,
)
from sqlbuild.compiler.refactoring.models import RefactorPlan


def stage_refactor_plan(
    *, project_dir: Path, staging_dir: Path, plan: RefactorPlan, copy_inputs: bool = True
) -> dict[str, str]:
    """Copy the project inputs once, apply the plan there, and return the original texts."""

    if copy_inputs:
        _ = copy_project_inputs(project_dir=project_dir, staging_dir=staging_dir)
    originals: dict[str, str] = read_originals(project_dir=project_dir, changes=plan.changes)
    _ = write_staged_changes(staging_dir=staging_dir, originals=originals, changes=plan.changes)
    return originals
