"""Virtual rollback public entrypoint."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledRelationTarget
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.main.views import refresh_logical_vde_views
from sqlbuild.virtual.planner.main.targets import build_virtual_target_from_physical_relation
from sqlbuild.virtual.state.main.locks import acquire_virtual_environment_lease
from sqlbuild.virtual.state.main.release_lock import release_state_lease
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    StateLockLease,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def run_virtual_rollback(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    no_sql_validation: bool = False,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Rollback a VDE to the previous finalized checkpoint."""

    if on_progress is not None:
        on_progress("Compiling project...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    if on_progress is not None:
        on_progress("Compiled project.")
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in graph.project.models}
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    lease: StateLockLease | None = None
    try:
        if on_progress is not None:
            on_progress("Inspecting virtual state...")
        lease = acquire_virtual_environment_lease(
            backend,
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            owner_id=f"rollback:{uuid.uuid4()}",
            ttl=timedelta(minutes=10),
        )
        if lease is None:
            raise PlannerInputError(
                f"virtual environment '{virtual_environment_name}' is locked",
                code="S019",
            )
        current_refs: tuple[VirtualEnvironmentRefRecord, ...] = (
            backend.get_virtual_environment_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            )
        )
        if not current_refs:
            raise PlannerInputError(
                f"unknown virtual environment '{virtual_environment_name}'",
                code="S020",
            )
        current_ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in current_refs}
        checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...] = (
            backend.list_virtual_environment_checkpoints(
                state_connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
            )
        )
        target_checkpoint: VirtualEnvironmentCheckpointRecord | None = None
        target_checkpoint_refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...] = ()
        checkpoint: VirtualEnvironmentCheckpointRecord
        for checkpoint in checkpoints:
            checkpoint_refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...] = (
                backend.get_virtual_environment_checkpoint_refs(
                    state_connection,
                    schema=config.schema,
                    checkpoint_id=checkpoint.checkpoint_id,
                )
            )
            checkpoint_ref_map: dict[str, str] = {
                ref.model_name: ref.version_hash for ref in checkpoint_refs
            }
            if checkpoint_ref_map != current_ref_map:
                target_checkpoint = checkpoint
                target_checkpoint_refs = checkpoint_refs
                break
        if target_checkpoint is None:
            raise PlannerInputError(
                "no previous finalized checkpoint is available for rollback",
                code="S021",
            )
        physical_relations: dict[str, PhysicalRelationRecord] = _read_physical_relations(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=target_checkpoint_refs,
        )
        _validate_physical_relations_exist(
            adapter=adapter,
            connection_config=connection_config,
            models_by_name=models_by_name,
            physical_relations=physical_relations,
        )
        target_refs: tuple[VirtualEnvironmentRefRecord, ...] = tuple(
            VirtualEnvironmentRefRecord(
                virtual_environment_name=virtual_environment_name,
                model_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            for ref in target_checkpoint_refs
        )
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=virtual_environment_name,
                status=VirtualEnvironmentStatus.FINALIZED,
            ),
        )
        backend.replace_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            refs=target_refs,
        )
        target_ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in target_refs}
        rolled_back_models: tuple[str, ...] = tuple(
            sorted(
                model_name
                for model_name, version_hash in current_ref_map.items()
                if target_ref_map.get(model_name) != version_hash
            )
        )
        if on_progress is not None:
            on_progress("Inspected virtual state.")
    finally:
        if lease is not None:
            release_state_lease(
                backend,
                state_connection,
                schema=config.schema,
                lease=lease,
            )
        backend.close(state_connection)

    if on_progress is not None:
        on_progress("Refreshing target VDE views...")
    refresh_logical_vde_views(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        physical_relations=physical_relations,
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
    )
    if on_progress is not None:
        on_progress("Refreshed target VDE views.")
    return target_checkpoint.checkpoint_id, rolled_back_models


def _read_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    ref: VirtualEnvironmentCheckpointRefRecord
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        if relation is None:
            raise PlannerInputError(
                f"checkpoint references missing physical relation for model '{ref.model_name}'",
                code="S022",
            )
        relations[ref.model_name] = relation
    return relations


def _validate_physical_relations_exist(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    models_by_name: dict[str, CompiledModel],
    physical_relations: dict[str, PhysicalRelationRecord],
) -> None:
    connection: Any = adapter.connect(connection_config)
    try:
        model_name: str
        relation: PhysicalRelationRecord
        for model_name, relation in physical_relations.items():
            model: CompiledModel | None = models_by_name.get(model_name)
            if model is None:
                raise PlannerInputError(
                    f"checkpoint references unknown model '{model_name}'",
                    code="S023",
                )
            target: CompiledRelationTarget = build_virtual_target_from_physical_relation(
                adapter=adapter,
                relation=relation,
                fallback_target=model.target,
            )
            if not adapter.relation_exists(
                connection,
                database=target.database,
                schema=target.schema,
                name=target.name,
            ):
                raise PlannerInputError(
                    f"checkpoint references missing warehouse relation for model '{model_name}'",
                    code="S024",
                )
    finally:
        adapter.close(connection)
