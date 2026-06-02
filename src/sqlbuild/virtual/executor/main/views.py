"""Public helpers for logical VDE view refreshes."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationDestination
from sqlbuild.shared.helpers.naming import resolve_destination_qualified_name
from sqlbuild.virtual.executor.helpers.rewrite import build_virtual_destination
from sqlbuild.virtual.planner.main.targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def refresh_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_target_name: str,
    unsuffixed_virtual_target_name: str | None = None,
    physical_relations: dict[str, PhysicalRelationRecord],
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
) -> None:
    """Create or replace logical VDE views from tracked physical relations."""

    started_at: float = time.perf_counter()
    if on_connection_start is not None:
        on_connection_start(1)
    connection: Any
    try:
        connection = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.perf_counter() - started_at)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.perf_counter() - started_at)
    recorder: StatementRecorder = StatementRecorder()
    try:
        for model in project.models:
            relation: PhysicalRelationRecord | None = physical_relations.get(model.name)
            if relation is None:
                continue
            physical_target: CompiledRelationDestination = (
                build_virtual_destination_from_physical_relation(
                    adapter=adapter,
                    relation=relation,
                    fallback_target=model.destination,
                )
            )
            virtual_target: CompiledRelationDestination = build_virtual_destination(
                adapter=adapter,
                target=model.destination,
                virtual_target_name=virtual_target_name,
                unsuffixed_virtual_target_name=unsuffixed_virtual_target_name,
            )
            adapter.ensure_schema(
                connection,
                database=virtual_target.database,
                schema=virtual_target.schema,
                statement_recorder=recorder,
            )
            adapter.create_view_as(
                connection,
                target=resolve_destination_qualified_name(adapter=adapter, target=virtual_target),
                sql=(
                    "SELECT * FROM "
                    + resolve_destination_qualified_name(adapter=adapter, target=physical_target)
                ),
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)
