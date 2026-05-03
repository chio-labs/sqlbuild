"""Build executor constants."""

from __future__ import annotations

from sqlbuild.compiler.planner.types import PlanAction

INCREMENTAL_ACTIONS: frozenset[PlanAction] = frozenset(
    {
        PlanAction.INCREMENTAL_APPEND,
        PlanAction.INCREMENTAL_DELETE_INSERT,
        PlanAction.INCREMENTAL_MERGE,
    }
)
