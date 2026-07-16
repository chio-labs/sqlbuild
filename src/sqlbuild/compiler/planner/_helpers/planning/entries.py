"""Plan entry construction phase for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.planner._helpers.output.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner._helpers.reuse.dependency_baseline import (
    build_dependency_baseline_entries,
    build_existing_destination_input_entries,
)
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    DependencyBaselinePlanEntry,
    ExistingDestinationInputPlanEntry,
    PlanEntryBuildInputs,
    PlannerChangeReconciliation,
    PlannerEntryResults,
    PlannerIdentityContext,
    PlannerModelEntryResults,
    PlannerOverrides,
    PlannerPolicies,
    PlannerRelationsContext,
    PlannerReuseResolution,
    PlannerRuntime,
    PlannerScope,
    PlannerScopePruningResult,
    PlannerWarehouseState,
    RunDespiteUnchangedPlanningResult,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult


def build_planner_entry_results(
    *,
    runtime: PlannerRuntime,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    overrides: PlannerOverrides,
    policies: PlannerPolicies,
    deferral: DeferralInputs,
    reuse: PlannerReuseResolution,
    pruning: PlannerScopePruningResult,
    reconciliation: PlannerChangeReconciliation,
    source_freshness: StandardSourceFreshnessPlanningResult,
) -> PlannerEntryResults:
    """Build execution model entries plus dependency-baseline and reuse-input entries."""

    dependency_baseline_scope: PlannerScope = replace(
        pruning.inspection_scope,
        selected_keys=reuse.reusable_dependency_baseline_keys,
    )
    execution_relations: PlannerRelationsContext = build_planner_relations_context(
        project=runtime.project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        scope=pruning.execution_scope,
        deferral=deferral,
        project_config=runtime.project_config,
        local_config=runtime.local_config,
        known_source_columns=warehouse.inspection_relations.source_warehouse_columns,
    )
    dependency_baseline_relations: PlannerRelationsContext = build_planner_relations_context(
        project=runtime.project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        scope=dependency_baseline_scope,
        deferral=deferral,
        project_config=runtime.project_config,
        local_config=runtime.local_config,
        known_source_columns=warehouse.inspection_relations.source_warehouse_columns,
    )
    dependency_baseline_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=runtime.project,
        adapter=runtime.adapter,
        scope=dependency_baseline_scope,
        snapshot=warehouse.snapshot,
        relations=dependency_baseline_relations,
        resolved_actions=reconciliation.resolved_actions,
        cursor_overrides=overrides.cursor_overrides,
        full_refresh=overrides.full_refresh,
        build_inputs=PlanEntryBuildInputs(
            standard_reuse_decisions=(
                reuse.standard_reuse.decisions if reuse.standard_reuse is not None else None
            ),
            run_despite_unchanged=RunDespiteUnchangedPlanningResult(),
            custom_prepare_version_materializations=(
                policies.custom_prepare_version_materializations
            ),
        ),
    )
    dependency_baseline_entries: tuple[DependencyBaselinePlanEntry, ...] = (
        build_dependency_baseline_entries(
            entries=dependency_baseline_entry_results.entries,
            candidate_keys=reuse.reusable_dependency_baseline_keys,
        )
    )
    existing_destination_input_entries: tuple[ExistingDestinationInputPlanEntry, ...] = (
        build_existing_destination_input_entries(
            scope=pruning.inspection_scope,
            candidate_keys=reuse.dependency_baseline_candidate_keys,
            reusable_keys=reuse.reusable_dependency_baseline_keys,
            existing_relation_names=frozenset(warehouse.snapshot.existing_relations),
            expected_version_hashes=identities.version_identities.model_version_hashes,
            destination_fingerprints=warehouse.snapshot.fingerprints.models,
        )
        if policies.enable_reuse_planning
        else ()
    )
    model_entry_results: PlannerModelEntryResults = build_plan_entries(
        project=runtime.project,
        adapter=runtime.adapter,
        scope=pruning.execution_scope,
        snapshot=warehouse.snapshot,
        relations=execution_relations,
        resolved_actions=reconciliation.resolved_actions,
        cursor_overrides=overrides.cursor_overrides,
        full_refresh=overrides.full_refresh,
        build_inputs=PlanEntryBuildInputs(
            standard_reuse_decisions=(
                reuse.standard_reuse.decisions if reuse.standard_reuse is not None else None
            ),
            run_despite_unchanged=pruning.run_despite_unchanged,
            source_freshness_blocked_model_names=(
                source_freshness.propagation.blocked_model_names
                if source_freshness.propagation is not None
                else frozenset()
            ),
            external_blocked_model_names=frozenset(overrides.external_blocked_model_names),
            custom_prepare_version_materializations=(
                policies.custom_prepare_version_materializations
            ),
        ),
    )
    return PlannerEntryResults(
        model_entry_results=model_entry_results,
        dependency_baseline_entries=dependency_baseline_entries,
        existing_destination_input_entries=existing_destination_input_entries,
    )
