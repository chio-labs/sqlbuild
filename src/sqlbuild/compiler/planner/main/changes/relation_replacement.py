"""Public incremental relation-replacement predicate."""

from __future__ import annotations

from sqlbuild.compiler.planner.types import MaterializationType, PlanAction


def replaces_incremental_relation(
    *, materialization_type: MaterializationType, action: PlanAction
) -> bool:
    """Identify incremental replacements whose bounds must ignore the destination maximum."""

    return (
        materialization_type == MaterializationType.INCREMENTAL
        and action == PlanAction.CREATE_TABLE
    )
