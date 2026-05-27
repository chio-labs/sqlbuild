"""Virtual state detach helper logic."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name
from sqlbuild.spec.models.environments import resolve_environment_name
from sqlbuild.virtual.executor.main.logical_target import build_virtual_logical_target
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
    active_environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=None,
    )
    if active_environment_name is None:
        raise PlannerInputError("state detach requires an active environment", code="C260")
    environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        state_connection,
        schema=config.schema,
        virtual_environment_name=active_environment_name,
    )
    if environment is None or environment.status != VirtualEnvironmentStatus.FINALIZED:
        raise PlannerInputError(
            "state detach requires a finalized virtual environment",
            code="C261",
        )
    operation_id: str = f"detach:{active_environment_name}"
    record_state_operation(
        backend,
        state_connection,
        schema=config.schema,
        operation_id=operation_id,
        operation_type=StateOperationType.DETACH,
        status=StateOperationStatus.RUNNING,
        action="start",
        virtual_environment_name=active_environment_name,
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
            virtual_environment_name=active_environment_name,
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
                target=resolve_target_qualified_name(
                    adapter=adapter,
                    target=build_virtual_logical_target(
                        adapter=adapter,
                        target=model.target,
                        virtual_environment_name=active_environment_name,
                        unsuffixed_virtual_environment_name=active_environment_name,
                    ),
                ),
                statement_recorder=recorder,
            )
            physical_target: CompiledRelationTarget = CompiledRelationTarget(
                database=relation.database_name,
                schema=relation.schema_name,
                name=relation.relation_name,
                qualified_name=relation.relation_name,
            )
            adapter.move_or_copy_relation(
                connection,
                source=resolve_target_qualified_name(adapter=adapter, target=physical_target),
                target=resolve_target_qualified_name(adapter=adapter, target=model.target),
                remove_source=False,
                allow_copy_fallback=allow_copy,
                statement_recorder=recorder,
            )
            detached_count += 1
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=active_environment_name,
                status=VirtualEnvironmentStatus.DETACHED,
                baseline_virtual_environment_name=environment.baseline_virtual_environment_name,
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
            virtual_environment_name=None,
            message=f"detached {detached_count} models",
        )
        return (
            f"Detached {detached_count} models from virtual environment {active_environment_name}."
        )
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
