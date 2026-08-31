"""Top-level planner orchestration producing an execution plan."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
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
)
from sqlbuild.compiler.planner._helpers.planning.reconciliation import reconcile_execution_changes
from sqlbuild.compiler.planner._helpers.planning.retention import plan_retention
from sqlbuild.compiler.planner._helpers.planning.scope_pruning import prune_planner_execution_scope
from sqlbuild.compiler.planner._helpers.planning.scopes import resolve_planner_scopes
from sqlbuild.compiler.planner._helpers.planning.warehouse_state import (
    gather_planner_warehouse_state,
)
from sqlbuild.compiler.planner._helpers.pruning.cascade import resolve_cascades
from sqlbuild.compiler.planner._helpers.warehouse.source_freshness import (
    build_planner_source_freshness_result,
)
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerChangeReconciliation,
    PlannerChangeResults,
    PlannerEntryResults,
    PlannerIdentityContext,
    PlannerOverrides,
    PlannerPolicies,
    PlannerResolvedActions,
    PlannerRuntime,
    PlannerScopePruningResult,
    PlannerScopeResolution,
    PlannerSelection,
    PlannerWarehouseState,
    PlanOutput,
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
    scopes: PlannerScopeResolution = resolve_planner_scopes(
        project=project,
        selection=selection,
        policies=policies,
    )
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
    )
    stale_warning_changes: PlannerChangeResults = detect_stale_warning_changes(
        project=project,
        scopes=scopes,
        snapshot=warehouse.snapshot,
        identities=identities,
    )
    check_selected_scope_buildability(
        project=project,
        scopes=scopes,
        snapshot=warehouse.snapshot,
        deferral=deferral,
    )
    changes: PlannerChangeResults = detect_changes(
        project=project,
        scope=scopes.inspection_scope,
        snapshot=warehouse.snapshot,
        full_refresh=overrides.full_refresh,
        expected_version_hashes=identities.version_identities.model_version_hashes,
        expected_metadata_jsons=identities.version_identities.model_metadata_jsons,
    )
    resolved_actions: PlannerResolvedActions = resolve_cascades(
        scope=scopes.inspection_scope,
        changes=changes,
    )
    source_freshness: DirectSourceFreshnessPlanningResult = build_planner_source_freshness_result(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scopes.inspection_scope,
        relations=warehouse.inspection_relations,
        freshness_state_schemas=warehouse.snapshot.source_freshness_state_schemas,
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
    plan_output: PlanOutput = assemble_base_plan_output(
        runtime=runtime,
        warehouse=warehouse,
        identities=identities,
        overrides=overrides,
        pruning=pruning,
        reconciliation=reconciliation,
        entries=entries,
        source_freshness=source_freshness,
    )
    plan_output = replace(
        plan_output,
        retention_entries=plan_retention(
            runtime=runtime, warehouse=warehouse, scope=scopes.selected_scope
        ),
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
    )
    plan_output = with_plan_metadata(
        plan_output=plan_output,
        pruning=pruning,
        source_freshness=source_freshness,
    )
    if on_progress is not None:
        on_progress(f"Generated plan. ({time.monotonic() - plan_start:.2f}s)")
    return plan_output
