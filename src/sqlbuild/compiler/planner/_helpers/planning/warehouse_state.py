"""Warehouse inspection phase for execution planning."""

from __future__ import annotations

import time

from sqlbuild.compiler.planner._helpers.migrations.columns import plan_column_migrations
from sqlbuild.compiler.planner._helpers.migrations.old_names import plan_old_name_views
from sqlbuild.compiler.planner._helpers.migrations.planning import plan_model_migrations
from sqlbuild.compiler.planner._helpers.output.plan_entry import build_planner_relations_context
from sqlbuild.compiler.planner._helpers.planning.full_refresh import (
    effectively_full_refreshed_model_names,
)
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import gather_warehouse_snapshot
from sqlbuild.compiler.planner.classes.migration_fingerprint_cache import (
    MigrationFingerprintCache,
)
from sqlbuild.compiler.planner.models import (
    ColumnMigrationPlanning,
    CursorSnapshotScope,
    DeferralInputs,
    ModelMigrationPlanning,
    OldNameViewPlanning,
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
    fingerprints: MigrationFingerprintCache = MigrationFingerprintCache(
        root=runtime.project.compile_cache_dir
    )
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
    migrations: ModelMigrationPlanning = plan_model_migrations(
        runtime=runtime,
        scope=scopes.selected_scope,
        snapshot=snapshot,
        overrides=overrides,
        deferral=deferral,
        fingerprints=fingerprints,
    )
    fingerprints.persist()
    inspection_relations: PlannerRelationsContext = build_planner_relations_context(
        project=runtime.project,
        adapter=runtime.adapter,
        connection=runtime.connection,
        scope=scopes.inspection_scope,
        deferral=deferral,
        project_config=runtime.project_config,
        local_config=runtime.local_config,
    )
    columns: ColumnMigrationPlanning = plan_column_migrations(
        runtime=runtime,
        scope=scopes.selected_scope,
        snapshot=migrations.snapshot,
        full_refresh_model_names=effectively_full_refreshed_model_names(
            project=runtime.project,
            cli_full_refresh=overrides.full_refresh,
        ),
        physical_relations={
            entry.model_name: entry.origin.qualified_name or entry.origin.name
            for entry in migrations.entries
            if entry.decision.moves_data
        },
        overrides=overrides,
        deferral=deferral,
        source_columns=inspection_relations.source_warehouse_columns,
    )
    old_names: OldNameViewPlanning = plan_old_name_views(
        runtime=runtime,
        scope=scopes.selected_scope,
        snapshot=snapshot,
        migration_entries=migrations.entries,
        column_entries=columns.entries,
    )
    if runtime.on_progress is not None:
        runtime.on_progress(
            f"Inspected warehouse state. ({time.monotonic() - warehouse_start:.2f}s)"
        )
        runtime.on_progress("Generating plan...")
    return PlannerWarehouseState(
        snapshot=columns.snapshot,
        inspection_relations=inspection_relations,
        migration_entries=migrations.entries,
        migration_warnings=(*migrations.warnings, *columns.warnings, *old_names.warnings),
        column_migration_entries=columns.entries,
        column_rename_hints=columns.hints,
        old_name_view_entries=old_names.entries,
        old_name_views=old_names.views,
        migration_fingerprints=fingerprints,
    )
