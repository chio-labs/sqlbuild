"""Public helpers for logical VDE view refreshes."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationLocation
from sqlbuild.shared.helpers.identity.naming import resolve_relation_location_qualified_name
from sqlbuild.shared.types import ConnectionElapsedCallback
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_destination_from_physical_relation,
    build_virtual_destination,
)
from sqlbuild.virtual.planner.main.targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.state.models import PhysicalRelationRecord


def refresh_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None = None,
    physical_relations: dict[str, PhysicalRelationRecord],
    seed_physical_relations: dict[str, PhysicalRelationRecord] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
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
            on_connection_error(1, elapsed_seconds=time.perf_counter() - started_at)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, elapsed_seconds=time.perf_counter() - started_at)
    recorder: StatementRecorder = StatementRecorder()
    try:
        seed_relation_map: dict[str, PhysicalRelationRecord] = seed_physical_relations or {}
        for model in project.models:
            relation: PhysicalRelationRecord | None = physical_relations.get(model.name)
            if relation is None:
                continue
            physical_target: CompiledRelationLocation = (
                build_virtual_destination_from_physical_relation(
                    adapter=adapter,
                    relation=relation,
                    fallback_target=model.destination,
                )
            )
            virtual_target: CompiledRelationLocation = build_virtual_destination(
                adapter=adapter,
                target=model.destination,
                virtual_environment_name=virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            )
            adapter.ensure_schema(
                connection=connection,
                database=virtual_target.database,
                schema=virtual_target.schema,
                statement_recorder=recorder,
            )
            adapter.create_view_as(
                connection=connection,
                destination=resolve_relation_location_qualified_name(
                    adapter=adapter, location=virtual_target
                ),
                sql=(
                    "SELECT * FROM "
                    + resolve_relation_location_qualified_name(
                        adapter=adapter, location=physical_target
                    )
                ),
                statement_recorder=recorder,
            )
        for seed in project.seeds:
            relation = seed_relation_map.get(seed.name)
            if relation is None:
                continue
            physical_target = build_destination_from_physical_relation(
                adapter=adapter,
                relation=relation,
                fallback_target=seed.destination,
            )
            virtual_target = build_virtual_destination(
                adapter=adapter,
                target=seed.destination,
                virtual_environment_name=virtual_environment_name,
                unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
            )
            adapter.ensure_schema(
                connection=connection,
                database=virtual_target.database,
                schema=virtual_target.schema,
                statement_recorder=recorder,
            )
            adapter.create_view_as(
                connection=connection,
                destination=resolve_relation_location_qualified_name(
                    adapter=adapter, location=virtual_target
                ),
                sql=(
                    "SELECT * FROM "
                    + resolve_relation_location_qualified_name(
                        adapter=adapter, location=physical_target
                    )
                ),
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)
