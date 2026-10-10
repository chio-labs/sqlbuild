"""Run each refactoring step natively under the `refactoring` stage, or with the Python planner."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands._helpers.refactor.native import (
    commit_native_refactor,
    migrate_native_refactor,
    plan_native_refactor,
    stage_native_refactor,
)
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.refactoring.main.commit_refactor_plan import commit_refactor_plan
from sqlbuild.compiler.refactoring.main.plan_column_rename import plan_column_rename
from sqlbuild.compiler.refactoring.main.plan_model_refactor import plan_model_refactor
from sqlbuild.compiler.refactoring.main.stage_refactor_plan import stage_refactor_plan
from sqlbuild.compiler.refactoring.main.with_model_migration import with_model_migration
from sqlbuild.compiler.refactoring.models import RefactorPlan, RefactorProject, RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation


def plan_refactor(
    *, project: RefactorProject, request: RefactorRequest
) -> tuple[RefactorPlan, str | None]:
    """Plan natively when the stage runs and can, else with Python; return the native JSON too."""

    if native_stage_enabled(NativeStage.REFACTORING):
        native: tuple[RefactorPlan, str] | None = plan_native_refactor(
            project=project, request=request
        )
        if native is not None:
            return native
    if request.operation == RefactorOperation.RENAME_COLUMN:
        return plan_column_rename(project=project, request=request), None
    return plan_model_refactor(project=project, request=request), None


def stage_plan(
    *,
    project_dir: Path,
    staging_dir: Path,
    plan: RefactorPlan,
    plan_json: str | None,
    copy_inputs: bool = True,
) -> dict[str, str]:
    """Stage a plan in the scratch copy and return the original texts."""

    if plan_json is not None:
        return stage_native_refactor(
            project_dir=project_dir,
            staging_dir=staging_dir,
            plan_json=plan_json,
            copy_inputs=copy_inputs,
        )
    return stage_refactor_plan(
        project_dir=project_dir, staging_dir=staging_dir, plan=plan, copy_inputs=copy_inputs
    )


def migrate_plan(
    *,
    plan: RefactorPlan,
    plan_json: str | None,
    before: RefactorProject,
    after: RefactorProject | None,
    originals: dict[str, str],
) -> tuple[RefactorPlan, str | None]:
    """Add model `migrate_from` to a staged rename whenever its relation moves."""

    if plan_json is not None:
        return migrate_native_refactor(
            plan_json=plan_json, before=before, after=after, originals=originals
        )
    return (
        with_model_migration(
            plan=plan,
            before=before.graph.project,
            after=after.graph.project if after is not None else None,
            originals=originals,
        ),
        None,
    )


def commit_plan(
    *, project_dir: Path, originals: dict[str, str], plan: RefactorPlan, plan_json: str | None
) -> None:
    """Write a verified plan into the project, restoring every file if a write fails."""

    if plan_json is not None:
        commit_native_refactor(project_dir=project_dir, originals=originals, plan_json=plan_json)
        return
    _ = commit_refactor_plan(project_dir=project_dir, originals=originals, plan=plan)
