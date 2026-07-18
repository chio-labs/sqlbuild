"""Shared VDE view refresh and function publish phase for executor runs."""

from __future__ import annotations

import time
from typing import Any

import sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name as rn
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.virtual.executor._helpers.rewrite import (
    build_destination_from_physical_relation,
    build_virtual_destination,
)
from sqlbuild.virtual.executor._helpers.rollback import publish_function_versions
from sqlbuild.virtual.executor.main._views import refresh_logical_vde_views
from sqlbuild.virtual.executor.models import VirtualEnvironmentPhysicalRelations
from sqlbuild.virtual.state.models import FunctionVersionRecord, PhysicalRelationRecord


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

    physical_targets: dict[str, CompiledRelationLocation] = {
        model.name: plan_output.model_locations.get(model.name, model.destination)
        for model in project.models
    }
    connection: Any = adapter.connect(connection_config)
    recorder: StatementRecorder = StatementRecorder()
    try:
        model: CompiledModel
        for model in project.models:
            if model.name not in final_version_hashes:
                continue
            physical_target: CompiledRelationLocation | None = physical_targets.get(model.name)
            if physical_target is None:
                continue
            virtual_target: CompiledRelationLocation = build_virtual_destination(
                adapter=adapter,
                target=model.destination,
                virtual_environment_name=target_vde_name,
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
        for seed in project.seeds:
            relation: PhysicalRelationRecord | None = final_seed_physical_relations.get(seed.name)
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
                virtual_environment_name=target_vde_name,
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
    refresh_logical_vde_views(
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
