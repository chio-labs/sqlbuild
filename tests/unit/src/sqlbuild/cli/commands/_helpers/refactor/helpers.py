"""Refactor output test builders."""

from __future__ import annotations

from sqlbuild.compiler.refactoring.models import FileChange, RefactorPlan, RefactorRequest
from sqlbuild.compiler.refactoring.types import RefactorOperation


def build_move_plan(*, changed_files: int) -> RefactorPlan:
    """Return a move plan that changes the given number of files."""

    return RefactorPlan(
        request=RefactorRequest(
            operation=RefactorOperation.MOVE_MODEL,
            model_name="orders",
            new_name="",
            destination="models/marts/orders.sql",
        ),
        changes=tuple(
            FileChange(
                path=f"models/orders_{index}.sql", original_path=f"models/orders_{index}.sql"
            )
            for index in range(changed_files)
        ),
    )
