"""Standard unchanged-scope pruning phase for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.planner.models import (
    PlannerResolvedActions,
    PlannerScope,
    PlannerScopePruningResult,
    PlannerScopeResolution,
    RunDespiteUnchangedPlanningResult,
)


def prune_planner_execution_scope(
    *,
    scopes: PlannerScopeResolution,
    resolved_actions: PlannerResolvedActions,
) -> PlannerScopePruningResult:
    """Derive the execution scope from the resolved inspection scope."""

    inspection_scope: PlannerScope = scopes.inspection_scope
    execution_scope: PlannerScope = replace(
        inspection_scope,
        selected_keys=inspection_scope.selected_keys - scopes.dependency_baseline_candidate_keys,
    )
    return PlannerScopePruningResult(
        inspection_scope=inspection_scope,
        execution_scope=execution_scope,
        resolved_actions=resolved_actions,
        pruned_standard_model_names=(),
        standard_identity_stale_model_names=frozenset(),
        run_despite_unchanged=RunDespiteUnchangedPlanningResult(),
    )
