"""Standard unchanged-scope pruning phase for execution planning."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.pruning.standard_scope import (
    build_standard_identity_stale_model_names,
    mark_direct_parent_run_actions,
    mark_run_despite_unchanged_actions,
    mark_version_identity_stale_actions,
    prune_standard_unchanged_scope,
)
from sqlbuild.compiler.planner.main.changes.run_despite_unchanged import (
    build_run_despite_unchanged_planning_result,
)
from sqlbuild.compiler.planner.models import (
    PlannerChangeResults,
    PlannerIdentityContext,
    PlannerOverrides,
    PlannerPolicies,
    PlannerResolvedActions,
    PlannerScope,
    PlannerScopePruningResult,
    PlannerScopeResolution,
    PlannerWarehouseState,
    RunDespiteUnchangedPlanningResult,
)
from sqlbuild.compiler.planner.types import StandardScopePruning
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult


def prune_planner_execution_scope(
    *,
    scopes: PlannerScopeResolution,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    overrides: PlannerOverrides,
    policies: PlannerPolicies,
    stale_warning_changes: PlannerChangeResults,
    resolved_actions: PlannerResolvedActions,
    source_freshness: StandardSourceFreshnessPlanningResult,
) -> PlannerScopePruningResult:
    """Prune unchanged nodes for stale-only planning and derive the execution scope."""

    inspection_scope: PlannerScope = scopes.inspection_scope
    pruned_standard_model_names: tuple[str, ...] = ()
    if (
        policies.standard_scope_pruning == StandardScopePruning.PRUNE_UNCHANGED
        and not overrides.full_refresh
    ):
        original_selected_model_names: frozenset[str] = frozenset(
            key.name
            for key in inspection_scope.selected_keys
            if key.resource_type == CompiledResourceType.MODEL
        )
        standard_identity_stale_model_names: frozenset[str] = (
            build_standard_identity_stale_model_names(
                scope=inspection_scope,
                expected_version_hashes=identities.version_identities.model_version_hashes,
                built_version_hashes={
                    model_name: fingerprint.version_hash
                    for model_name, fingerprint in warehouse.snapshot.fingerprints.models.items()
                },
                forced_stale_model_names=overrides.forced_stale_model_names,
            )
        )
        source_stale_model_names: frozenset[str] = (
            source_freshness.propagation.stale_model_names
            if source_freshness.propagation is not None
            else frozenset()
        )
        run_despite_unchanged: RunDespiteUnchangedPlanningResult = (
            build_run_despite_unchanged_planning_result(
                scope=inspection_scope,
                source_freshness=source_freshness,
                already_stale_model_names=(
                    standard_identity_stale_model_names | source_stale_model_names
                ),
                now=(
                    source_freshness.observed_records[0].observed_at
                    if source_freshness.observed_records
                    else datetime.now(UTC)
                ),
            )
        )
        inspection_scope = prune_standard_unchanged_scope(
            scope=inspection_scope,
            changes=stale_warning_changes,
            resolved_actions=resolved_actions,
            source_freshness=source_freshness,
            run_despite_unchanged=run_despite_unchanged,
            forced_stale_model_names=overrides.forced_stale_model_names,
            expected_version_hashes=identities.version_identities.model_version_hashes,
            expected_seed_version_hashes=identities.version_identities.seed_version_hashes,
            built_seed_fingerprints=warehouse.snapshot.fingerprints.seeds,
        )
        pruned_standard_model_names = tuple(
            sorted(
                original_selected_model_names
                - frozenset(
                    key.name
                    for key in inspection_scope.selected_keys
                    if key.resource_type == CompiledResourceType.MODEL
                )
            )
        )
        resolved_actions = mark_version_identity_stale_actions(
            scope=inspection_scope,
            resolved_actions=resolved_actions,
            expected_version_hashes=identities.version_identities.model_version_hashes,
            forced_stale_model_names=overrides.forced_stale_model_names,
        )
        resolved_actions = mark_run_despite_unchanged_actions(
            scope=inspection_scope,
            resolved_actions=resolved_actions,
            run_despite_unchanged=run_despite_unchanged,
        )
        resolved_actions = mark_direct_parent_run_actions(
            scope=inspection_scope,
            resolved_actions=resolved_actions,
        )
    else:
        standard_identity_stale_model_names = frozenset()
        run_despite_unchanged = RunDespiteUnchangedPlanningResult()
    execution_scope: PlannerScope = replace(
        inspection_scope,
        selected_keys=inspection_scope.selected_keys - scopes.dependency_baseline_candidate_keys,
    )
    return PlannerScopePruningResult(
        inspection_scope=inspection_scope,
        execution_scope=execution_scope,
        resolved_actions=resolved_actions,
        pruned_standard_model_names=pruned_standard_model_names,
        standard_identity_stale_model_names=standard_identity_stale_model_names,
        run_despite_unchanged=run_despite_unchanged,
    )
