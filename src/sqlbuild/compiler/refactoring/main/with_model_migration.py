"""Add model migrate_from to a staged rename whenever its relation moves."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.refactoring._helpers.renames.model_planning import decide_model_migration
from sqlbuild.compiler.refactoring._helpers.text.header_edits import insert_header_entry_edit
from sqlbuild.compiler.refactoring.constants import MIGRATE_FROM_KEY
from sqlbuild.compiler.refactoring.models import (
    FileChange,
    ManualLocation,
    MigrationDeclaration,
    ModelMigrationDecision,
    RefactorPlan,
    TextEdit,
)


def with_model_migration(
    *,
    plan: RefactorPlan,
    before: CompiledProject,
    after: CompiledProject | None,
    originals: dict[str, str],
) -> RefactorPlan:
    """Return the plan with `migrate_from <old>` on the model whenever its relation moves."""

    old: str = plan.request.model_name
    new: str = plan.request.new_name
    decision: ModelMigrationDecision = decide_model_migration(
        before=before, after=after, old=old, new=new
    )
    change: FileChange | None = next(
        (item for item in plan.changes if item.path == plan.request.destination), None
    )
    if decision.blocked:
        return replace(
            plan,
            blocking=(
                *plan.blocking,
                ManualLocation(
                    path=plan.request.destination or "",
                    line=None,
                    column=None,
                    reason=decision.reason,
                ),
            ),
        )
    if not decision.needed or change is None:
        return plan
    declaration: str = f"{MIGRATE_FROM_KEY} {old}"
    edit: TextEdit | None = insert_header_entry_edit(
        contents=originals[change.original_path], entry=declaration, display=declaration
    )
    if edit is None:
        return replace(
            plan,
            blocking=(
                *plan.blocking,
                ManualLocation(
                    path=change.path,
                    line=1,
                    column=1,
                    reason=f"add {declaration} to the MODEL header to keep history",
                ),
            ),
        )
    return replace(
        plan,
        changes=tuple(
            replace(item, edits=(*item.edits, edit)) if item is change else item
            for item in plan.changes
        ),
        migrations=(
            *plan.migrations,
            MigrationDeclaration(model_name=new, declaration=declaration, reason=decision.reason),
        ),
    )
