"""Public warehouse discovery planner phase entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.planner.helpers.scope import build_planner_scope
from sqlbuild.compiler.planner.helpers.warehouse_snapshot import build_warehouse_snapshot
from sqlbuild.compiler.planner.models import (
    PlannerScope,
    PlannerWarehouseSnapshotResult,
    WarehouseSnapshot,
)


def build_warehouse_snapshot_phase(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection: Any,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    auto_load_sources: bool = False,
    full_refresh: bool = False,
    start_cursor_override: str | None = None,
    end_cursor_override: str | None = None,
    on_progress: Callable[[str], None] | None = None,
    deferred_targets: dict[str, CompiledRelationLocation] | None = None,
    deferred_relations: dict[str, RelationInfo] | None = None,
) -> PlannerWarehouseSnapshotResult:
    scope: PlannerScope = build_planner_scope(
        project=project,
        select=select,
        exclude=exclude,
        auto_load_sources=auto_load_sources,
    )
    snapshot: WarehouseSnapshot = build_warehouse_snapshot(
        project=project,
        adapter=adapter,
        connection=connection,
        scope=scope,
        full_refresh=full_refresh,
        start_cursor_override=start_cursor_override,
        end_cursor_override=end_cursor_override,
        on_progress=on_progress,
        deferred_targets=deferred_targets,
        deferred_relations=deferred_relations,
    )
    return PlannerWarehouseSnapshotResult(scope=scope, snapshot=snapshot)
