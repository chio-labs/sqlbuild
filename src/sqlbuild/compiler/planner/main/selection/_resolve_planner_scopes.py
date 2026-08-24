"""Planner scope resolution entrypoint for compiler orchestration."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner._helpers.planning.scopes import (
    resolve_planner_scopes as _resolve_planner_scopes,
)
from sqlbuild.compiler.planner.models import (
    PlannerPolicies,
    PlannerScopeResolution,
    PlannerSelection,
)


def resolve_planner_scopes(
    *,
    project: CompiledProject,
    selection: PlannerSelection,
    policies: PlannerPolicies,
) -> PlannerScopeResolution:
    """Resolve selected, stale-warning, and inspection scopes for one plan."""

    return _resolve_planner_scopes(
        project=project,
        selection=selection,
        policies=policies,
    )
