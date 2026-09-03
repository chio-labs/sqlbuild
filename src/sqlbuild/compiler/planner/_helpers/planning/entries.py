"""Plan entry construction phase for execution planning."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.output.plan_entry import (
    build_plan_entries,
    build_planner_relations_context,
)
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlanEntryBuildInputs,
    PlannerChangeReconciliation,
    PlannerEntryResults,
    PlannerIdentityContext,
    PlannerModelEntryResults,
    PlannerOverrides,
    PlannerPolicies,
    PlannerRelationsContext,
    PlannerRuntime,
    PlannerScopePruningResult,
    PlannerWarehouseState,
)
from sqlbuild.compiler.source_freshness.models import DirectSourceFreshnessPlanningResult


def build_planner_entry_results(
    *,
    runtime: PlannerRuntime,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    overrides: PlannerOverrides,
    policies: PlannerPolicies,
    deferral: DeferralInputs,
    pruning: PlannerScopePruningResult,
    reconciliation: PlannerChangeReconciliation,
    source_freshness: DirectSourceFreshnessPlanningResult,
) -> PlannerEntryResults:
    """Build execution model entries for one plan build."""

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
            run_despite_unchanged=pruning.run_despite_unchanged,
            source_freshness_blocked_model_names=(
                source_freshness.propagation.blocked_model_names
                if source_freshness.propagation is not None
                else frozenset()
            ),
            external_blocked_model_names=frozenset(overrides.external_blocked_model_names),
            future_cursor_config=(
                runtime.project_config.cursors.future
                if runtime.project_config is not None
                else None
            ),
            start_cursor_config=(
                runtime.project_config.cursors.start if runtime.project_config is not None else None
            ),
            invocation_time=runtime.invocation_time,
            max_microbatches=(
                overrides.max_microbatches
                if overrides.max_microbatches is not None
                else (
                    runtime.project_config.microbatches.limits.max_batches
                    if runtime.project_config is not None
                    else None
                )
            ),
            max_microbatches_is_override=overrides.max_microbatches is not None,
            microbatch_limit_action=(
                runtime.project_config.microbatches.limits.action
                if runtime.project_config is not None
                else PlanEntryBuildInputs().microbatch_limit_action
            ),
        ),
    )
    return PlannerEntryResults(
        model_entry_results=model_entry_results,
    )
