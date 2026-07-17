"""Virtual state detach helper logic."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import RelationType
from sqlbuild.adapter.relations.main.resolve_relation_location_qualified_name import (
    resolve_relation_location_qualified_name,
)
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.spec.contracts.main.resolve_target_name import resolve_target_name
from sqlbuild.virtual.executor.main._logical_target import build_virtual_logical_destination
from sqlbuild.virtual.executor.main._relation_type import resolve_model_relation_type
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.environments._record_operation import record_state_operation
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    StateBackendConfig,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import (
    StateOperationStatus,
    StateOperationType,
    VirtualEnvironmentStatus,
)


def detach_from_virtual_state(
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
        raise PlannerInputError("state detach requires an active target", code="C260")
    environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        connection=state_connection,
        schema=config.schema,
        virtual_environment_name=active_target_name,
    )
    if environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED:
        raise PlannerInputError(
            "state detach requires a finalized virtual environment",
            code="C261",
        )
    operation_id: str = f"detach:{active_target_name}"
    record_state_operation(
        backend=backend,
        connection=state_connection,
        schema=config.schema,
        operation_id=operation_id,
        operation_type=StateOperationType.DETACH,
        status=StateOperationStatus.RUNNING,
        action="start",
        virtual_environment_name=active_target_name,
        message="starting detach",
    )
    try:
        graph: ProjectGraph = build_project_graph(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
        )
        refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
                connection=state_connection,
                schema=config.schema,
                virtual_environment_name=active_target_name,
            )
        )
        ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in refs}
        recorder: StatementRecorder = StatementRecorder()
        detached_count: int = 0
        for model in graph.project.models:
            version_hash: str | None = ref_map.get(model.name)
            if version_hash is None:
                continue
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                connection=state_connection,
                schema=config.schema,
                model_name=model.name,
                version_hash=version_hash,
            )
            if relation is None:
                continue
            adapter.drop_view(
                connection=connection,
                destination=resolve_relation_location_qualified_name(
                    adapter=adapter,
                    location=build_virtual_logical_destination(
                        adapter=adapter,
                        target=model.destination,
                        virtual_environment_name=active_target_name,
                        unsuffixed_virtual_environment_name=active_target_name,
                    ),
                ),
                statement_recorder=recorder,
            )
            model_relation_type: str = resolve_model_relation_type(
                str(model.config.values.get("materialized", "table"))
            )
            if model_relation_type == RelationType.VIEW:
                adapter.create_view_as(
                    connection=connection,
                    destination=resolve_relation_location_qualified_name(
                        adapter=adapter, location=model.destination
                    ),
                    sql=model.query_sql,
                    statement_recorder=recorder,
                )
                detached_count += 1
                continue
            physical_target: CompiledRelationLocation = CompiledRelationLocation(
                database=relation.database_name,
                schema=relation.schema_name,
                name=relation.relation_name,
                qualified_name=relation.relation_name,
            )
            adapter.move_or_copy_relation(
                connection=connection,
                origin=resolve_relation_location_qualified_name(
                    adapter=adapter, location=physical_target
                ),
                destination=resolve_relation_location_qualified_name(
                    adapter=adapter, location=model.destination
                ),
                remove_origin=False,
                allow_copy_fallback=allow_copy,
                statement_recorder=recorder,
            )
            detached_count += 1
        backend.upsert_virtual_environment(
            connection=state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=active_target_name,
                status=VirtualEnvironmentStatus.DETACHED,
                baseline_virtual_environment_name=environment.baseline_virtual_environment_name,
                finalized_at=environment.finalized_at,
            ),
        )
        record_state_operation(
            backend=backend,
            connection=state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.SUCCEEDED,
            action="finish",
            virtual_environment_name=None,
            message=f"detached {detached_count} models",
        )
        return f"Detached {detached_count} models from virtual environment {active_target_name}."
    except BaseException as error:
        record_state_operation(
            backend=backend,
            connection=state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.FAILED,
            action="fail",
            virtual_environment_name=None,
            message=str(error),
        )
        raise
