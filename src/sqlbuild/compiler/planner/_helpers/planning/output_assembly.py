"""Plan output assembly phases for execution planning."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.migrations.entry_fingerprints import (
    with_migration_fingerprints,
)
from sqlbuild.compiler.planner._helpers.output.plan_output import build_plan_output
from sqlbuild.compiler.planner._helpers.planning.retention import plan_retention, plan_table_types
from sqlbuild.compiler.planner._helpers.pruning.selection_staleness import (
    build_stale_out_of_selection_warnings,
)
from sqlbuild.compiler.planner._helpers.warehouse.source_freshness_warnings import (
    build_source_freshness_unknown_warnings,
)
from sqlbuild.compiler.planner.models import (
    ColumnRenameHint,
    ModelPlanEntry,
    PlannedSqlTests,
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
    planned_sql_tests: PlannedSqlTests | None = None,
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
            planned_sql_tests=planned_sql_tests,
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


def with_storage_policies(
    *,
    plan_output: PlanOutput,
    runtime: PlannerRuntime,
    warehouse: PlannerWarehouseState,
    scopes: PlannerScopeResolution,
    policies: PlannerPolicies,
) -> PlanOutput:
    """Attach migrations and selected Snowflake table-type and retention work to the plan."""

    return replace(
        plan_output,
        model_entries=with_column_rename_hints(
            entries=with_migration_fingerprints(
                entries=plan_output.model_entries,
                models_by_name={model.name: model for model in runtime.project.models},
                fingerprints=warehouse.migration_fingerprints,
                dialect=runtime.adapter.sql_analysis_dialect(),
            )
            if policies.record_migration_fingerprints
            else plan_output.model_entries,
            hints=warehouse.column_rename_hints,
        ),
        migration_entries=warehouse.migration_entries,
        column_migration_entries=warehouse.column_migration_entries,
        old_name_view_entries=warehouse.old_name_view_entries,
        old_name_views=warehouse.old_name_views,
        warnings=(*warehouse.migration_warnings, *plan_output.warnings),
        table_type_entries=plan_table_types(
            runtime=runtime, warehouse=warehouse, scope=scopes.selected_scope
        ),
        retention_entries=plan_retention(
            runtime=runtime, warehouse=warehouse, scope=scopes.selected_scope
        ),
    )


def with_column_rename_hints(
    *, entries: tuple[ModelPlanEntry, ...], hints: tuple[ColumnRenameHint, ...]
) -> tuple[ModelPlanEntry, ...]:
    """Attach near-match column rename hints to the model entries they describe."""

    by_model: dict[str, list[ColumnRenameHint]] = {}
    hint: ColumnRenameHint
    for hint in hints:
        by_model.setdefault(hint.model_name, []).append(hint)
    return tuple(
        replace(entry, column_rename_hints=tuple(by_model[entry.name]))
        if entry.name in by_model
        else entry
        for entry in entries
    )


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
    """Append source freshness and stale-out-of-selection warnings to the plan."""

    freshness_warnings: tuple[PlanWarning, ...] = build_source_freshness_unknown_warnings(
        source_freshness=source_freshness
    )
    if freshness_warnings:
        plan_output = replace(
            plan_output,
            warnings=(*plan_output.warnings, *freshness_warnings),
        )
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
            model_changes_complete=True,
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
            pruning.direct_identity_stale_model_names
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
        "unknown_source_details": tuple(
            {
                "source_name": unknown.source_name,
                "reason": unknown.reason.value,
                "message": unknown.message,
            }
            for unknown in source_freshness.unknown_sources.values()
        ),
        "age_warning_source_names": age_warning_source_names,
        "age_error_source_names": age_error_source_names,
        "stale_model_names": stale_model_names,
        "blocked_model_names": blocked_model_names,
    }
