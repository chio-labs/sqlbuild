"""Virtual state adopt helper logic."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name
from sqlbuild.spec.models.targets import resolve_target_name
from sqlbuild.virtual.executor.main.logical_target import build_virtual_logical_destination
from sqlbuild.virtual.executor.main.physical_target import build_virtual_physical_destination
from sqlbuild.virtual.executor.main.relation_type import resolve_model_relation_type
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.record_operation import record_state_operation
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    StateBackendConfig,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import (
    ModelVersionStatus,
    StateOperationStatus,
    StateOperationType,
    VirtualEnvironmentStatus,
)


def adopt_into_virtual_state(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    config: StateBackendConfig,
    backend: StateBackend,
    state_connection: Any,
    adapter: BaseAdapter,
    connection: Any,
    allow_copy: bool,
) -> str:
    active_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    if active_target_name is None:
        raise PlannerInputError("state adopt requires an active target", code="C259")
    operation_id: str = f"adopt:{active_target_name}"
    record_state_operation(
        backend,
        state_connection,
        schema=config.schema,
        operation_id=operation_id,
        operation_type=StateOperationType.ADOPT,
        status=StateOperationStatus.RUNNING,
        action="start",
        virtual_environment_name=active_target_name,
        message="starting adopt",
    )
    try:
        graph: ProjectGraph = build_project_graph(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
        )
        refs: list[VirtualEnvironmentRefRecord] = []
        recorder: StatementRecorder = StatementRecorder()
        for model in graph.project.models:
            if not adapter.relation_exists(
                connection,
                database=model.destination.database,
                schema=model.destination.schema,
                name=model.destination.name,
            ):
                continue
            version_hash: str = model.name
            physical_target: CompiledRelationLocation = build_virtual_physical_destination(
                adapter=adapter,
                target=model.destination,
                model_name=model.name,
                version_hash=version_hash,
            )
            adapter.ensure_schema(
                connection,
                database=physical_target.database,
                schema=physical_target.schema,
                statement_recorder=recorder,
            )
            model_relation_type: str = resolve_model_relation_type(
                str(model.config.values.get("materialized", "table"))
            )
            adapter.move_or_copy_relation(
                connection,
                source=resolve_relation_location_qualified_name(
                    adapter=adapter, location=model.destination
                ),
                target=resolve_relation_location_qualified_name(
                    adapter=adapter, location=physical_target
                ),
                remove_source=model_relation_type != "view",
                allow_copy_fallback=allow_copy,
                statement_recorder=recorder,
            )
            if model_relation_type == "view":
                adapter.drop_view(
                    connection,
                    target=resolve_relation_location_qualified_name(
                        adapter=adapter, location=model.destination
                    ),
                    statement_recorder=recorder,
                )
            virtual_target: CompiledRelationLocation = build_virtual_logical_destination(
                adapter=adapter,
                target=model.destination,
                virtual_environment_name=active_target_name,
                unsuffixed_virtual_environment_name=active_target_name,
            )
            adapter.create_view_as(
                connection,
                target=resolve_relation_location_qualified_name(
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
            backend.upsert_model_version(
                state_connection,
                schema=config.schema,
                record=ModelVersionRecord(
                    model_name=model.name,
                    version_hash=version_hash,
                    data_hash=version_hash,
                    metadata_hash=version_hash,
                    status=ModelVersionStatus.READY,
                ),
            )
            backend.upsert_physical_relation(
                state_connection,
                schema=config.schema,
                record=PhysicalRelationRecord(
                    model_name=model.name,
                    version_hash=version_hash,
                    database_name=physical_target.database,
                    schema_name=physical_target.schema or "",
                    relation_name=physical_target.name,
                    relation_type="table",
                ),
            )
            refs.append(
                VirtualEnvironmentRefRecord(
                    virtual_environment_name=active_target_name,
                    model_name=model.name,
                    version_hash=version_hash,
                )
            )
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=active_target_name,
                status=VirtualEnvironmentStatus.FINALIZED,
            ),
        )
        backend.replace_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=active_target_name,
            refs=tuple(refs),
        )
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.SUCCEEDED,
            action="finish",
            virtual_environment_name=None,
            message=f"adopted {len(refs)} models",
        )
        return f"Adopted {len(refs)} models into virtual environment {active_target_name}."
    except BaseException as error:
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.FAILED,
            action="fail",
            virtual_environment_name=None,
            message=str(error),
        )
        raise
