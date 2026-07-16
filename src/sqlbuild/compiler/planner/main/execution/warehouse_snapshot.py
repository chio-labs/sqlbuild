"""Public warehouse discovery planner phase entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.planner._helpers.graph.scope import build_planner_scope
from sqlbuild.compiler.planner._helpers.warehouse.snapshot import build_warehouse_snapshot
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
    on_progress: Callable[[str], None] | None = None,
    deferred_locations: dict[str, CompiledRelationLocation] | None = None,
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
        on_progress=on_progress,
        deferred_locations=deferred_locations,
        deferred_relations=deferred_relations,
    )
    return PlannerWarehouseSnapshotResult(scope=scope, snapshot=snapshot)
