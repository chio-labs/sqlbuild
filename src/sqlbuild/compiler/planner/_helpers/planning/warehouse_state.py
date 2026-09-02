"""Warehouse inspection phase for execution planning."""

from __future__ import annotations

import time

from sqlbuild.compiler.planner._helpers.output.plan_entry import build_planner_relations_context
from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    effectively_full_refreshed_model_names,
)
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import gather_warehouse_snapshot
from sqlbuild.compiler.planner.models import (
    CursorSnapshotScope,
    DeferralInputs,
    PlannerOverrides,
    PlannerRelationsContext,
    PlannerRuntime,
    PlannerScopeResolution,
    PlannerWarehouseState,
    WarehouseSnapshot,
)


def gather_planner_warehouse_state(
    *,
    runtime: PlannerRuntime,
    scopes: PlannerScopeResolution,
    overrides: PlannerOverrides,
    deferral: DeferralInputs,
) -> PlannerWarehouseState:
    """Gather the warehouse snapshot and inspection relations in one pass."""

    warehouse_start: float = time.monotonic()
    if runtime.on_progress is not None:
        runtime.on_progress("Inspecting warehouse state...")
    snapshot: WarehouseSnapshot = gather_warehouse_snapshot(
        project=runtime.project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        execute=runtime.adapter.execute,
        selected_keys=frozenset(scopes.stale_warning_scope.all_keys.values()),
        full_refresh_model_names=effectively_full_refreshed_model_names(
            project=runtime.project,
            cli_full_refresh=overrides.full_refresh,
        ),
        on_progress=runtime.on_progress,
        deferred_locations=deferral.deferred_locations,
        cursor_scope=CursorSnapshotScope(
            model_keys=scopes.selected_scope.selected_keys,
            runtime_producer_keys=scopes.selected_scope.selected_keys,
            invocation_time=runtime.invocation_time,
            start_cursor_config=(
                runtime.project_config.cursors.start if runtime.project_config is not None else None
            ),
            cursor_overrides=overrides.cursor_overrides,
        ),
    )
    inspection_relations: PlannerRelationsContext = build_planner_relations_context(
        project=runtime.project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        scope=scopes.inspection_scope,
        deferral=deferral,
        project_config=runtime.project_config,
        local_config=runtime.local_config,
    )
    if runtime.on_progress is not None:
        runtime.on_progress(
            f"Inspected warehouse state. ({time.monotonic() - warehouse_start:.2f}s)"
        )
        runtime.on_progress("Generating plan...")
    return PlannerWarehouseState(snapshot=snapshot, inspection_relations=inspection_relations)
