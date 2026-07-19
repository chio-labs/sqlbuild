"""Shared VDE view refresh and function publish phase for executor runs."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name as rn
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.virtual.executor._helpers.rewrite import build_virtual_destination
from sqlbuild.virtual.executor._helpers.rollback import publish_function_versions
from sqlbuild.virtual.executor.models import VirtualEnvironmentPhysicalRelations
from sqlbuild.virtual.planner.main._targets import (
    build_virtual_destination_from_physical_relation,
)
from sqlbuild.virtual.state.models import FunctionVersionRecord, PhysicalRelationRecord


def write_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    model_physical_locations: dict[str, CompiledRelationLocation],
    seed_physical_locations: dict[str, CompiledRelationLocation],
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
) -> None:
    """Create or replace logical VDE views from resolved physical locations."""

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
    view_entries: list[tuple[CompiledRelationLocation, CompiledRelationLocation]] = []
    for model in project.models:
        model_location: CompiledRelationLocation | None = model_physical_locations.get(model.name)
        if model_location is not None:
            view_entries.append((model.destination, model_location))
    for seed in project.seeds:
        seed_location: CompiledRelationLocation | None = seed_physical_locations.get(seed.name)
        if seed_location is not None:
            view_entries.append((seed.destination, seed_location))
    try:
        for destination, physical_target in view_entries:
            virtual_target: CompiledRelationLocation = build_virtual_destination(
                adapter=adapter,
                target=destination,
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
                destination=rn.resolve_relation_location_qualified_name(
                    adapter=adapter, location=virtual_target
                ),
                sql=(
                    "SELECT * FROM "
                    + rn.resolve_relation_location_qualified_name(
                        adapter=adapter, location=physical_target
                    )
                ),
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)


def write_vde_views_from_records(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    physical_relations: dict[str, PhysicalRelationRecord],
    seed_physical_relations: dict[str, PhysicalRelationRecord],
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: ConnectionElapsedCallback | None = None,
    on_connection_error: ConnectionElapsedCallback | None = None,
) -> None:
    """Create or replace logical VDE views from tracked physical relation records."""

    model_locations: dict[str, CompiledRelationLocation] = {}
    for model in project.models:
        model_relation: PhysicalRelationRecord | None = physical_relations.get(model.name)
        if model_relation is None:
            continue
        model_locations[model.name] = build_virtual_destination_from_physical_relation(
            adapter=adapter,
            relation=model_relation,
            fallback_target=model.destination,
        )
    seed_locations: dict[str, CompiledRelationLocation] = {}
    for seed in project.seeds:
        seed_relation: PhysicalRelationRecord | None = seed_physical_relations.get(seed.name)
        if seed_relation is None:
            continue
        seed_locations[seed.name] = build_virtual_destination_from_physical_relation(
            adapter=adapter,
            relation=seed_relation,
            fallback_target=seed.destination,
        )
    write_vde_views(
        project=project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        model_physical_locations=model_locations,
        seed_physical_locations=seed_locations,
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
    )


def write_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    target_vde_name: str,
    unsuffixed_virtual_environment_name: str | None,
    plan_output: PlanOutput,
    final_version_hashes: dict[str, str],
    final_seed_physical_relations: dict[str, PhysicalRelationRecord],
) -> None:
    """Write logical model and seed views for finalized physical versions."""

    model_locations: dict[str, CompiledRelationLocation] = {}
    for model in project.models:
        if model.name not in final_version_hashes:
            continue
        model_locations[model.name] = plan_output.model_locations.get(model.name, model.destination)
    seed_locations: dict[str, CompiledRelationLocation] = {}
    for seed in project.seeds:
        relation: PhysicalRelationRecord | None = final_seed_physical_relations.get(seed.name)
        if relation is None:
            continue
        seed_locations[seed.name] = build_virtual_destination_from_physical_relation(
            adapter=adapter,
            relation=relation,
            fallback_target=seed.destination,
        )
    write_vde_views(
        project=project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=target_vde_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        model_physical_locations=model_locations,
        seed_physical_locations=seed_locations,
    )


def write_virtual_environment_views(
    *,
    graph: ProjectGraph,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    unsuffixed_virtual_environment_name: str | None,
    relations: VirtualEnvironmentPhysicalRelations,
    function_versions: dict[str, FunctionVersionRecord],
    hooks: ConnectionHooks,
) -> None:
    """Refresh target VDE views and publish the given function versions."""

    refresh_start: float = time.perf_counter()
    if hooks.on_progress is not None:
        hooks.on_progress("Refreshing target VDE views...")
    write_vde_views_from_records(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        physical_relations=relations.model_relations,
        seed_physical_relations=relations.seed_relations,
        on_connection_start=hooks.on_connection_start,
        on_connection_complete=hooks.on_connection_complete,
        on_connection_error=hooks.on_connection_error,
    )
    if function_versions:
        publish_function_versions(
            adapter=adapter,
            connection_config=connection_config,
            graph=graph,
            virtual_environment_name=virtual_environment_name,
            function_versions=function_versions,
        )
    if hooks.on_progress is not None:
        hooks.on_progress(
            f"Refreshed target VDE views. ({time.perf_counter() - refresh_start:.2f}s)"
        )
