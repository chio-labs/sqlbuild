"""Plan a column rename from compiler facts, one step or cascading through pass-throughs."""

from __future__ import annotations

from sqlbuild.compiler.refactoring._helpers.columns.column_planning import (
    column_rename_context,
    column_rename_parts,
)
from sqlbuild.compiler.refactoring._helpers.text.text_edits import build_plan
from sqlbuild.compiler.refactoring.constants import COLUMN_MANUAL_HELP
from sqlbuild.compiler.refactoring.models import (
    ColumnRenameContext,
    RefactorParts,
    RefactorPlan,
    RefactorProject,
    RefactorRequest,
)


def plan_column_rename(*, project: RefactorProject, request: RefactorRequest) -> RefactorPlan:
    """Plan every edit that renames one output column and its downstream references."""

    context: ColumnRenameContext = column_rename_context(project=project, request=request)
    parts: RefactorParts = column_rename_parts(context=context)
    return build_plan(
        request=request,
        parts=parts,
        moves={},
        renamed_columns=tuple((model, context.old, context.new) for model in parts.cascaded),
        help=COLUMN_MANUAL_HELP,
    )
