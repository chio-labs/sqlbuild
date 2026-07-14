"""Reading persisted virtual bound state for one planning run."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.models import RelationInfo
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.runtime.contracts.types import ConnectionElapsedCallback
from sqlbuild.spec.resolution.main.resolve_target_name import resolve_target_name
from sqlbuild.virtual.freshness.main.current_records import (
    build_current_virtual_source_freshness_records,
)
from sqlbuild.virtual.planner._helpers.planning import (
    build_bound_version_hashes,
    build_source_freshness_unchanged_source_names,
)
from sqlbuild.virtual.planner._helpers.state_metadata import read_previous_function_query_sqls
from sqlbuild.virtual.planner._helpers.targets import build_destination_from_physical_relation
from sqlbuild.virtual.planner.models import VirtualBoundState
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    SourceFreshnessRecord,
)


def resolve_virtual_environment_name(
    *,
    physical_target_name: str | None,
    virtual_environment_name: str | None,
) -> str | None:
    """Resolve the VDE name, defaulting to the physical target name."""

    return virtual_environment_name or physical_target_name


def read_virtual_bound_state(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    adapter: BaseAdapter,
    warehouse_connection: Any,
    graph: ProjectGraph,
    selected_target: str | None,
    virtual_environment_name: str | None,
) -> VirtualBoundState:
    """Read bound refs, versions, freshness, and deferrals from virtual state."""

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        physical_target_name: str | None = resolve_target_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            selected_target=selected_target,
        )
        target_name: str | None = resolve_virtual_environment_name(
            physical_target_name=physical_target_name,
            virtual_environment_name=virtual_environment_name,
        )
        if target_name is None:
            return VirtualBoundState()
        refs: tuple[Any, ...] = backend.get_virtual_environment_model_refs(
            connection=state_connection,
            schema=config.schema,
            virtual_environment_name=target_name,
        )
        bound_version_hashes: dict[str, str] = build_bound_version_hashes(refs)
        seed_refs: tuple[Any, ...] = backend.get_virtual_environment_seed_refs(
            connection=state_connection,
            schema=config.schema,
            virtual_environment_name=target_name,
        )
        previous_source_freshness_records: tuple[SourceFreshnessRecord, ...] = (
            backend.get_virtual_environment_source_freshness(
                connection=state_connection,
                schema=config.schema,
                virtual_environment_name=target_name,
            )
        )
        source_freshness_records: tuple[SourceFreshnessRecord, ...] = (
            build_current_virtual_source_freshness_records(
                adapter=adapter,
                connection=warehouse_connection,
                sources=tuple(source.source_entry for source in graph.project.sources),
                virtual_environment_name=target_name,
                observed_at=datetime.now(),
                previous_records=previous_source_freshness_records,
            )
        )
        model_versions: dict[str, ModelVersionRecord | None] = {
            model_name: backend.get_model_version(
                connection=state_connection,
                schema=config.schema,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in bound_version_hashes.items()
        }
        model_locations: dict[str, CompiledRelationLocation] = {
            model.name: model.destination for model in graph.project.models
        }
        physical_relations: dict[str, PhysicalRelationRecord] = {}
        for model_name, version_hash in bound_version_hashes.items():
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                connection=state_connection,
                schema=config.schema,
                model_name=model_name,
                version_hash=version_hash,
            )
            if relation is not None:
                physical_relations[model_name] = relation
        return VirtualBoundState(
            refs=refs,
            seed_refs=seed_refs,
            model_versions=model_versions,
            source_freshness_records=source_freshness_records,
            source_freshness_unchanged_source_names=(
                build_source_freshness_unchanged_source_names(
                    previous_records=previous_source_freshness_records,
                    current_records=source_freshness_records,
                )
            ),
            deferred_locations={
                model_name: build_destination_from_physical_relation(
                    adapter=adapter,
                    relation=relation,
                    fallback_target=model_locations[model_name],
                )
                for model_name, relation in physical_relations.items()
                if model_name in model_locations
            },
            deferred_relations={
                model_name: RelationInfo(
                    database=relation.database_name,
                    schema=relation.schema_name,
                    name=relation.relation_name,
                    relation_type=relation.relation_type,
                )
                for model_name, relation in physical_relations.items()
            },
            previous_function_query_sqls=read_previous_function_query_sqls(
                backend=backend,
                state_connection=state_connection,
                schema=config.schema,
                graph=graph,
                virtual_environment_name=target_name,
            ),
        )
    finally:
        backend.close(state_connection)


def open_planning_connection(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    on_connection_start: Callable[[int], None] | None,
    on_connection_complete: ConnectionElapsedCallback | None,
    on_connection_error: ConnectionElapsedCallback | None,
) -> Any:
    """Open one warehouse connection for planning with progress callbacks."""

    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, elapsed_seconds=time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, elapsed_seconds=time.monotonic() - start)
    return connection
