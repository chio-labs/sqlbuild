"""Virtual state detach helper logic."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.naming import resolve_destination_qualified_name
from sqlbuild.spec.models.targets import resolve_target_name
from sqlbuild.virtual.executor.main.logical_target import build_virtual_logical_destination
from sqlbuild.virtual.executor.main.relation_type import resolve_model_relation_type
from sqlbuild.virtual.state.classes.state_backend import StateBackend
from sqlbuild.virtual.state.main.record_operation import record_state_operation
from sqlbuild.virtual.state.models import (
    PhysicalRelationRecord,
    StateBackendConfig,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
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
        raise PlannerInputError("state detach requires an active environment", code="C260")
    environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        state_connection,
        schema=config.schema,
        virtual_target_name=active_target_name,
    )
    if environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED:
        raise PlannerInputError(
            "state detach requires a finalized virtual environment",
            code="C261",
        )
    operation_id: str = f"detach:{active_target_name}"
    record_state_operation(
        backend,
        state_connection,
        schema=config.schema,
        operation_id=operation_id,
        operation_type=StateOperationType.DETACH,
        status=StateOperationStatus.RUNNING,
        action="start",
        virtual_target_name=active_target_name,
        message="starting detach",
    )
    try:
        graph: ProjectGraph = build_project_graph(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
        )
        refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_target_name=active_target_name,
        )
        ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in refs}
        recorder: StatementRecorder = StatementRecorder()
        detached_count: int = 0
        for model in graph.project.models:
            version_hash: str | None = ref_map.get(model.name)
            if version_hash is None:
                continue
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                state_connection,
                schema=config.schema,
                model_name=model.name,
                version_hash=version_hash,
            )
            if relation is None:
                continue
            adapter.drop_view(
                connection,
                target=resolve_destination_qualified_name(
                    adapter=adapter,
                    target=build_virtual_logical_destination(
                        adapter=adapter,
                        target=model.target,
                        virtual_target_name=active_target_name,
                        unsuffixed_virtual_target_name=active_target_name,
                    ),
                ),
                statement_recorder=recorder,
            )
            model_relation_type: str = resolve_model_relation_type(
                str(model.config.values.get("materialized", "table"))
            )
            if model_relation_type == "view":
                adapter.create_view_as(
                    connection,
                    target=resolve_destination_qualified_name(adapter=adapter, target=model.target),
                    sql=model.query_sql,
                    statement_recorder=recorder,
                )
                detached_count += 1
                continue
            physical_target: CompiledRelationDestination = CompiledRelationDestination(
                database=relation.database_name,
                schema=relation.schema_name,
                name=relation.relation_name,
                qualified_name=relation.relation_name,
            )
            adapter.move_or_copy_relation(
                connection,
                source=resolve_destination_qualified_name(adapter=adapter, target=physical_target),
                target=resolve_destination_qualified_name(adapter=adapter, target=model.target),
                remove_source=False,
                allow_copy_fallback=allow_copy,
                statement_recorder=recorder,
            )
            detached_count += 1
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_target_name=active_target_name,
                status=VirtualEnvironmentStatus.DETACHED,
                baseline_virtual_target_name=environment.baseline_virtual_target_name,
                finalized_at=environment.finalized_at,
            ),
        )
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.SUCCEEDED,
            action="finish",
            virtual_target_name=None,
            message=f"detached {detached_count} models",
        )
        return f"Detached {detached_count} models from virtual environment {active_target_name}."
    except BaseException as error:
        record_state_operation(
            backend,
            state_connection,
            schema=config.schema,
            operation_id=operation_id,
            operation_type=None,
            status=StateOperationStatus.FAILED,
            action="fail",
            virtual_target_name=None,
            message=str(error),
        )
        raise
