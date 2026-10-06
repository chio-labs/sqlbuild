"""Top-level planner orchestration producing an execution plan."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.relations.main.open_inspection_catalog import open_inspection_catalog
from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.changes.actions import resolve_model_actions
from sqlbuild.compiler.planner._helpers.changes.detect import detect_changes
from sqlbuild.compiler.planner._helpers.planning.buildability import (
    check_selected_scope_buildability,
)
from sqlbuild.compiler.planner._helpers.planning.entries import build_planner_entry_results
from sqlbuild.compiler.planner._helpers.planning.identities import (
    build_planner_identity_context,
    detect_stale_warning_changes,
)
from sqlbuild.compiler.planner._helpers.planning.output_assembly import (
    assemble_base_plan_output,
    with_plan_metadata,
    with_plan_warnings,
    with_storage_policies,
)
from sqlbuild.compiler.planner._helpers.planning.reconciliation import reconcile_execution_changes
from sqlbuild.compiler.planner._helpers.planning.scope_pruning import prune_planner_execution_scope
from sqlbuild.compiler.planner._helpers.planning.scopes import resolve_planner_scopes
from sqlbuild.compiler.planner._helpers.planning.warehouse_state import (
    gather_planner_warehouse_state,
)
from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    type_cursor_overrides,
)
from sqlbuild.compiler.planner._helpers.warehouse.source_freshness import (
    build_planner_source_freshness_result,
)
from sqlbuild.compiler.planner.classes.background_sql_test_planning import (
    BackgroundSqlTestPlanning,
)
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannedSqlTests,
    PlannerChangeReconciliation,
    PlannerChangeResults,
    PlannerEntryResults,
    PlannerIdentityContext,
    PlannerOverrides,
    PlannerPolicies,
    PlannerResolvedActions,
    PlannerRuntime,
    PlannerScope,
    PlannerScopePruningResult,
    PlannerScopeResolution,
    PlannerSelection,
    PlannerWarehouseState,
    PlanOutput,
    WarehouseSnapshot,
)
from sqlbuild.compiler.source_freshness.models import DirectSourceFreshnessPlanningResult
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def build_execution_plan(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    selection: PlannerSelection,
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
    policies: PlannerPolicies,
    on_progress: Callable[[str], None] | None = None,
    project_config: ProjectConfig | None = None,
    local_config: LocalConfig | None = None,
) -> PlanOutput:
    runtime: PlannerRuntime = PlannerRuntime(
        project=project,
        adapter=adapter,
        connection=connection,
        project_config=project_config,
        local_config=local_config,
        on_progress=on_progress,
    )
    scopes: PlannerScopeResolution
    scopes, overrides = _resolve_scopes_and_cursor_overrides(
        project=project,
        selection=selection,
        policies=policies,
        overrides=overrides,
    )
    with (
        BackgroundSqlTestPlanning(
            project=project,
            adapter=adapter,
            selected_keys=scopes.inspection_scope.selected_keys,
            sql_test_selection=scopes.inspection_scope.sql_test_selection,
            enabled=policies.plan_sql_tests,
        ) as test_planning,
        open_inspection_catalog(adapter=adapter, connection=connection),
    ):
        warehouse: PlannerWarehouseState = gather_planner_warehouse_state(
            runtime=runtime,
            scopes=scopes,
            overrides=overrides,
            deferral=deferral,
        )
        plan_start: float = time.monotonic()
        identities: PlannerIdentityContext = build_planner_identity_context(
            project=project,
            scopes=scopes,
            include_stale_warning_identities=policies.selection_diagnostics,
        )
        check_selected_scope_buildability(
            runtime=runtime,
            scopes=scopes,
            warehouse=warehouse,
            deferral=deferral,
        )
        changes: PlannerChangeResults
        stale_warning_changes: PlannerChangeResults
        changes, stale_warning_changes = _detect_planner_change_results(
            project=project,
            scopes=scopes,
            snapshot=warehouse.snapshot,
            identities=identities,
            overrides=overrides,
            policies=policies,
        )
        resolved_actions: PlannerResolvedActions = resolve_model_actions(
            scope=scopes.inspection_scope,
            changes=changes,
        )
        source_freshness: DirectSourceFreshnessPlanningResult = (
            build_planner_source_freshness_result(
                project=project,
                adapter=adapter,
                connection=connection,
                scope=scopes.inspection_scope,
                relations=warehouse.inspection_relations,
                freshness_state_schemas=warehouse.snapshot.source_freshness_state_schemas,
            )
        )
        pruning: PlannerScopePruningResult = prune_planner_execution_scope(
            scopes=scopes,
            resolved_actions=resolved_actions,
        )
        reconciliation: PlannerChangeReconciliation = reconcile_execution_changes(
            warehouse=warehouse,
            identities=identities,
            pruning=pruning,
            changes=changes,
        )
        entries: PlannerEntryResults = build_planner_entry_results(
            runtime=runtime,
            warehouse=warehouse,
            identities=identities,
            overrides=overrides,
            policies=policies,
            deferral=deferral,
            pruning=pruning,
            reconciliation=reconciliation,
            source_freshness=source_freshness,
        )
        planned_sql_tests: PlannedSqlTests = test_planning.result()
        plan_output: PlanOutput = assemble_base_plan_output(
            runtime=runtime,
            warehouse=warehouse,
            identities=identities,
            overrides=overrides,
            pruning=pruning,
            reconciliation=reconciliation,
            entries=entries,
            source_freshness=source_freshness,
            planned_sql_tests=planned_sql_tests,
        )
        plan_output = with_storage_policies(
            plan_output=plan_output,
            runtime=runtime,
            warehouse=warehouse,
            scopes=scopes,
            policies=policies,
        )
        plan_output = with_plan_warnings(
            runtime=runtime,
            scopes=scopes,
            warehouse=warehouse,
            identities=identities,
            stale_warning_changes=stale_warning_changes,
            pruning=pruning,
            source_freshness=source_freshness,
            plan_output=plan_output,
            policies=policies,
        )
        plan_output = with_plan_metadata(
            plan_output=plan_output,
            pruning=pruning,
            source_freshness=source_freshness,
            policies=policies,
        )
        if on_progress is not None:
            on_progress(f"Generated plan. ({time.monotonic() - plan_start:.2f}s)")
        return plan_output


def _resolve_scopes_and_cursor_overrides(
    *,
    project: CompiledProject,
    selection: PlannerSelection,
    policies: PlannerPolicies,
    overrides: PlannerOverrides,
) -> tuple[PlannerScopeResolution, PlannerOverrides]:
    scopes: PlannerScopeResolution = resolve_planner_scopes(
        project=project,
        selection=selection,
        policies=policies,
    )
    selected_scope: PlannerScope = scopes.selected_scope
    selected_models: tuple[CompiledModel, ...] = tuple(
        selected_scope.models_by_name[key.name]
        for key in selected_scope.selected_keys
        if key.resource_type == CompiledResourceType.MODEL
        and key.name in selected_scope.models_by_name
    )
    return scopes, replace(
        overrides,
        cursor_overrides=type_cursor_overrides(
            cursor_overrides=overrides.cursor_overrides, selected_models=selected_models
        ),
    )


def _detect_planner_change_results(
    *,
    project: CompiledProject,
    scopes: PlannerScopeResolution,
    snapshot: WarehouseSnapshot,
    identities: PlannerIdentityContext,
    overrides: PlannerOverrides,
    policies: PlannerPolicies,
) -> tuple[PlannerChangeResults, PlannerChangeResults]:
    changes: PlannerChangeResults = detect_changes(
        project=project,
        scope=scopes.inspection_scope,
        snapshot=snapshot,
        full_refresh=overrides.full_refresh,
        expected_version_hashes=identities.version_identities.model_version_hashes,
        expected_metadata_jsons=identities.version_identities.model_metadata_jsons,
    )
    if not policies.selection_diagnostics:
        return changes, PlannerChangeResults(models={}, functions={})
    return changes, detect_stale_warning_changes(
        project=project,
        scopes=scopes,
        snapshot=snapshot,
        identities=identities,
        execution_changes=changes,
    )
