"""Virtual rollback helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledRelationDestination,
)
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.virtual.executor.helpers.functions import (
    decode_function_arguments,
    decode_function_body_sql,
    decode_function_language,
    decode_function_packages,
    decode_function_return_columns,
)
from sqlbuild.virtual.executor.helpers.rewrite import build_virtual_destination
from sqlbuild.virtual.planner.main.selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main.targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    PhysicalRelationRecord,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointRefRecord,
    VirtualEnvironmentRefRecord,
)


def resolve_target_checkpoint(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...],
    current_ref_map: dict[str, str],
    checkpoint_id: str | None,
) -> tuple[
    VirtualEnvironmentCheckpointRecord | None, tuple[VirtualEnvironmentCheckpointRefRecord, ...]
]:
    checkpoint: VirtualEnvironmentCheckpointRecord
    for checkpoint in checkpoints:
        if checkpoint_id is not None and checkpoint.checkpoint_id != checkpoint_id:
            continue
        checkpoint_refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...] = (
            backend.get_virtual_environment_checkpoint_refs(
                state_connection,
                schema=schema,
                checkpoint_id=checkpoint.checkpoint_id,
            )
        )
        checkpoint_ref_map: dict[str, str] = {
            ref.model_name: ref.version_hash for ref in checkpoint_refs
        }
        if checkpoint_id is not None or checkpoint_ref_map != current_ref_map:
            return checkpoint, checkpoint_refs
    if checkpoint_id is not None:
        raise PlannerInputError(f"unknown checkpoint '{checkpoint_id}'", code="S026")
    return None, ()


def resolve_selected_model_names(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_model_names: tuple[str, ...],
    target_checkpoint_refs: tuple[VirtualEnvironmentCheckpointRefRecord, ...],
) -> tuple[str, ...]:
    if select:
        return resolve_virtual_plan_model_selection(
            graph=graph,
            select=select,
            exclude=exclude,
            default_selection=all_model_names,
            stale_model_names=(),
        )
    excluded: set[str] = set(
        resolve_virtual_plan_model_selection(
            graph=graph,
            select=exclude,
            exclude=(),
            default_selection=(),
            stale_model_names=(),
        )
        if exclude
        else ()
    )
    return tuple(ref.model_name for ref in target_checkpoint_refs if ref.model_name not in excluded)


def stale_after_rollback(
    *,
    graph: ProjectGraph,
    final_version_hashes: dict[str, str],
    expected_version_hashes: dict[str, str],
) -> tuple[str, ...]:
    return tuple(
        model.name
        for model in graph.project.models
        if final_version_hashes.get(model.name) != expected_version_hashes.get(model.name)
    )


def guard_partial_rollback_scope(
    *,
    graph: ProjectGraph,
    selected_model_names: tuple[str, ...],
    stale_after: tuple[str, ...],
    checkpoint_ref_map: dict[str, str],
    final_version_hashes: dict[str, str],
    include_stale_upstreams: bool,
) -> tuple[str, ...]:
    checkpoint_mismatched_models: tuple[str, ...] = tuple(
        model_name
        for model_name, checkpoint_hash in checkpoint_ref_map.items()
        if final_version_hashes.get(model_name) != checkpoint_hash
    )
    required_upstreams: tuple[str, ...] = resolve_virtual_plan_model_selection(
        graph=graph,
        select=selected_model_names,
        exclude=(),
        default_selection=selected_model_names,
        stale_model_names=checkpoint_mismatched_models,
        include_stale_upstreams=True,
    )
    stale_upstream_set: set[str] = set(required_upstreams) - set(selected_model_names)
    if stale_upstream_set and not include_stale_upstreams:
        raise PlannerInputError(
            "selected rollback scope is missing stale required upstream models: "
            + ", ".join(sorted(stale_upstream_set)),
            code="S028",
            help="Re-run with --include-stale-upstreams to add required upstream refs.",
        )
    for model_name in stale_upstream_set:
        if model_name not in checkpoint_ref_map:
            raise PlannerInputError(
                "checkpoint is missing required upstream refs: " + model_name,
                code="S025",
            )
        final_version_hashes[model_name] = checkpoint_ref_map[model_name]
    return tuple(sorted({*selected_model_names, *stale_upstream_set}))


def read_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentRefRecord, ...],
) -> dict[str, Any]:
    return {
        ref.model_name: backend.get_model_version(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in refs
    }


def read_physical_relations(
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


def validate_physical_relations_exist(
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
            target: CompiledRelationDestination = build_virtual_destination_from_physical_relation(
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


def read_function_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...],
) -> dict[str, FunctionVersionRecord]:
    versions: dict[str, FunctionVersionRecord] = {}
    ref: VirtualEnvironmentCheckpointFunctionRefRecord
    for ref in refs:
        record: FunctionVersionRecord | None = backend.get_function_version(
            state_connection,
            schema=schema,
            function_name=ref.function_name,
            version_hash=ref.version_hash,
        )
        if record is None:
            raise PlannerInputError(
                f"checkpoint references missing function version for '{ref.function_name}'",
                code="S029",
            )
        versions[ref.function_name] = record
    return versions


def publish_function_versions(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    graph: ProjectGraph,
    virtual_target_name: str,
    function_versions: dict[str, FunctionVersionRecord],
) -> None:
    functions_by_name: dict[str, CompiledFunction] = {
        function.name: function for function in graph.project.functions
    }
    connection: Any = adapter.connect(connection_config)
    recorder: StatementRecorder = StatementRecorder()
    try:
        for function_name, record in function_versions.items():
            function: CompiledFunction | None = functions_by_name.get(function_name)
            if function is None:
                continue
            target: CompiledRelationDestination = build_virtual_destination(
                adapter=adapter,
                target=function.target,
                virtual_target_name=virtual_target_name,
            )
            adapter.ensure_schema(
                connection,
                database=target.database,
                schema=target.schema,
                statement_recorder=recorder,
            )
            if target.qualified_name is None:
                continue
            adapter.create_function(
                connection,
                target=target.qualified_name,
                arguments=decode_function_arguments(record),
                returns=record.returns,
                body_sql=decode_function_body_sql(record),
                return_columns=decode_function_return_columns(record),
                language=decode_function_language(record),
                runtime_version=record.runtime_version,
                entry_point=record.entry_point,
                packages=decode_function_packages(record),
                source_file_path=None,
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)
