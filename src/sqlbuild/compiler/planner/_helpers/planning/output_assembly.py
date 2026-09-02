"""Plan output assembly phases for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.output.plan_output import build_plan_output
from sqlbuild.compiler.planner._helpers.pruning.selection_staleness import (
    build_stale_out_of_selection_warnings,
)
from sqlbuild.compiler.planner.models import (
    PlannerChangeReconciliation,
    PlannerChangeResults,
    PlannerEntryResults,
    PlannerIdentityContext,
    PlannerOverrides,
    PlannerPolicies,
    PlannerRuntime,
    PlannerScopePruningResult,
    PlannerScopeResolution,
    PlannerWarehouseState,
    PlanOutput,
    PlanOutputExtras,
    PlanWarning,
    RunDespiteUnchangedPlanningResult,
)
from sqlbuild.compiler.source_freshness.models import DirectSourceFreshnessPlanningResult
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus


def assemble_base_plan_output(
    *,
    runtime: PlannerRuntime,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    overrides: PlannerOverrides,
    pruning: PlannerScopePruningResult,
    reconciliation: PlannerChangeReconciliation,
    entries: PlannerEntryResults,
    source_freshness: DirectSourceFreshnessPlanningResult,
) -> PlanOutput:
    """Assemble the base plan output with freshness and pruning metadata attached."""

    plan_output: PlanOutput = build_plan_output(
        project=runtime.project,
        adapter=runtime.adapter,
        scope=pruning.execution_scope,
        snapshot=warehouse.snapshot,
        relations=warehouse.inspection_relations,
        changes=reconciliation.changes,
        model_entry_results=entries.model_entry_results,
        reload_sources=overrides.reload_sources,
        extras=PlanOutputExtras(
            seed_version_hashes=identities.version_identities.seed_version_hashes,
            seed_metadata_jsons=identities.version_identities.seed_metadata_jsons,
        ),
    )
    plan_output = replace(plan_output, source_freshness=source_freshness)
    if pruning.pruned_direct_model_names:
        plan_output = replace(
            plan_output,
            metadata={
                **plan_output.metadata,
                "direct_pruned_model_names": pruning.pruned_direct_model_names,
            },
        )
    return plan_output


def with_plan_warnings(
    *,
    runtime: PlannerRuntime,
    scopes: PlannerScopeResolution,
    warehouse: PlannerWarehouseState,
    identities: PlannerIdentityContext,
    stale_warning_changes: PlannerChangeResults,
    pruning: PlannerScopePruningResult,
    source_freshness: DirectSourceFreshnessPlanningResult,
    plan_output: PlanOutput,
    policies: PlannerPolicies,
) -> PlanOutput:
    """Append stale-out-of-selection warnings to the plan."""

    if not policies.selection_diagnostics:
        return plan_output
    stale_out_of_selection_warnings: tuple[PlanWarning, ...] = (
        build_stale_out_of_selection_warnings(
            original_scope=scopes.stale_warning_scope,
            execution_scope=pruning.execution_scope,
            changes=stale_warning_changes,
            snapshot=warehouse.snapshot,
            version_identities=identities.stale_warning_identities,
            source_freshness=source_freshness,
            include_sources=False,
        )
    )
    if stale_out_of_selection_warnings:
        plan_output = replace(
            plan_output,
            warnings=(*plan_output.warnings, *stale_out_of_selection_warnings),
        )
    return plan_output


def with_plan_metadata(
    *,
    plan_output: PlanOutput,
    pruning: PlannerScopePruningResult,
    source_freshness: DirectSourceFreshnessPlanningResult,
    policies: PlannerPolicies,
) -> PlanOutput:
    """Attach direct source-freshness metadata to the plan output."""

    direct_remaining_stale_model_names: tuple[str, ...] = tuple(
        sorted(
            (
                pruning.direct_identity_stale_model_names
                | pruning.run_despite_unchanged.stale_model_names
            )
            - frozenset(
                key.name
                for key in pruning.inspection_scope.selected_keys
                if key.resource_type == CompiledResourceType.MODEL
            )
        )
    )
    plan_output = replace(
        plan_output,
        metadata={
            **plan_output.metadata,
            "direct_source_freshness": _serialize_direct_source_freshness_metadata(
                source_freshness
            ),
            "direct_remaining_stale_model_names": direct_remaining_stale_model_names,
            "direct_run_despite_unchanged": _serialize_run_despite_unchanged_metadata(
                pruning.run_despite_unchanged
            ),
            "selection_diagnostics": {
                "mode": "direct",
                "enabled": policies.selection_diagnostics,
            },
        },
    )
    return plan_output


def _serialize_direct_source_freshness_metadata(
    source_freshness: DirectSourceFreshnessPlanningResult,
) -> dict[str, object]:
    changed_source_names: tuple[str, ...] = tuple(
        sorted(identity.source_name for identity in source_freshness.changed_identities)
    )
    unchanged_source_names: tuple[str, ...] = tuple(
        sorted(identity.source_name for identity in source_freshness.unchanged_identities)
    )
    stale_model_names: tuple[str, ...] = (
        tuple(sorted(source_freshness.propagation.stale_model_names))
        if source_freshness.propagation is not None
        else ()
    )
    blocked_model_names: tuple[str, ...] = (
        tuple(sorted(source_freshness.propagation.blocked_model_names))
        if source_freshness.propagation is not None
        else ()
    )
    age_warning_source_names: tuple[str, ...] = tuple(
        sorted(
            identity.source_name
            for identity, status in source_freshness.age_statuses.items()
            if status == SourceFreshnessAgeStatus.WARN
        )
    )
    age_error_source_names: tuple[str, ...] = tuple(
        sorted(
            identity.source_name
            for identity, status in source_freshness.age_statuses.items()
            if status == SourceFreshnessAgeStatus.ERROR
        )
    )
    return {
        "observed_source_names": tuple(
            sorted(record.source_name for record in source_freshness.observed_records)
        ),
        "changed_source_names": changed_source_names,
        "unchanged_source_names": unchanged_source_names,
        "unknown_source_names": tuple(sorted(source_freshness.unknown_source_names)),
        "age_warning_source_names": age_warning_source_names,
        "age_error_source_names": age_error_source_names,
        "stale_model_names": stale_model_names,
        "blocked_model_names": blocked_model_names,
    }


def _serialize_run_despite_unchanged_metadata(
    run_despite_unchanged: RunDespiteUnchangedPlanningResult,
) -> dict[str, object]:
    return {
        "root_model_names": tuple(sorted(run_despite_unchanged.root_model_names)),
        "stale_model_names": tuple(sorted(run_despite_unchanged.stale_model_names)),
        "decisions": {
            model_name: {
                "mode": decision.mode.value,
                "duration": decision.duration,
                "newest_source_name": decision.newest_source_name,
                "newest_source_data_age_seconds": (decision.newest_source_data_age_seconds),
            }
            for model_name, decision in sorted(run_despite_unchanged.decisions.items())
        },
    }
