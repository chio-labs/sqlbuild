"""Virtual rollback helper functions."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.main.relation_lookup import build_relation_lookup
from sqlbuild.adapter.models import FunctionDefinition, RelationLookup
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.virtual.executor._helpers.functions import (
    decode_function_arguments,
    decode_function_body_sql,
    decode_function_language,
    decode_function_packages,
    decode_function_return_columns,
)
from sqlbuild.virtual.executor._helpers.promote import selected_upstream_seed_names
from sqlbuild.virtual.executor._helpers.rewrite import build_virtual_destination
from sqlbuild.virtual.executor.models import (
    RollbackCheckpointState,
    RollbackRefUpdate,
    RollbackResolution,
    VirtualEnvironmentPhysicalRelations,
)
from sqlbuild.virtual.planner.main.selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main.targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    PhysicalRelationRecord,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentCheckpointSeedRefRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentNodeRefRecord,
    VirtualEnvironmentRecord,
    VirtualEnvironmentSeedRefRecord,
)
from sqlbuild.virtual.state.types import PhysicalArtifactType, VirtualEnvironmentStatus


def resolve_target_checkpoint(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    checkpoints: tuple[VirtualEnvironmentCheckpointRecord, ...],
    current_ref_map: dict[str, str],
    checkpoint_id: str | None,
) -> tuple[
    VirtualEnvironmentCheckpointRecord | None,
    tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
]:
    checkpoint: VirtualEnvironmentCheckpointRecord
    for checkpoint in checkpoints:
        if checkpoint_id is not None and checkpoint.checkpoint_id != checkpoint_id:
            continue
        checkpoint_model_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...] = (
            backend.get_virtual_environment_checkpoint_model_refs(
                connection=state_connection,
                schema=schema,
                checkpoint_id=checkpoint.checkpoint_id,
            )
        )
        checkpoint_ref_map: dict[str, str] = {
            ref.model_name: ref.version_hash for ref in checkpoint_model_refs
        }
        if checkpoint_id is not None or checkpoint_ref_map != current_ref_map:
            return checkpoint, checkpoint_model_refs
    if checkpoint_id is not None:
        raise PlannerInputError(f"unknown checkpoint '{checkpoint_id}'", code="S026")
    return None, ()


def resolve_selected_model_names(
    *,
    graph: ProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_model_names: tuple[str, ...],
    target_checkpoint_model_refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
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
    return tuple(
        ref.model_name for ref in target_checkpoint_model_refs if ref.model_name not in excluded
    )


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
) -> tuple[tuple[str, ...], dict[str, str]]:
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
    return tuple(sorted({*selected_model_names, *stale_upstream_set})), final_version_hashes


def read_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentModelRefRecord, ...],
) -> dict[str, Any]:
    return {
        ref.model_name: backend.get_model_version(
            connection=state_connection,
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
    refs: tuple[VirtualEnvironmentCheckpointModelRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    ref: VirtualEnvironmentCheckpointModelRefRecord
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            connection=state_connection,
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


def read_seed_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    ref: VirtualEnvironmentCheckpointSeedRefRecord
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation_for_artifact(
            connection=state_connection,
            schema=schema,
            artifact_type=PhysicalArtifactType.SEED,
            artifact_name=ref.seed_name,
            version_hash=ref.version_hash,
        )
        if relation is None:
            raise PlannerInputError(
                f"checkpoint references missing physical relation for seed '{ref.seed_name}'",
                code="S022",
            )
        relations[ref.seed_name] = relation
    return relations


def validate_physical_relations_exist(
    *,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    models_by_name: dict[str, CompiledModel],
    physical_relations: dict[str, PhysicalRelationRecord],
) -> None:
    targets_by_model: dict[str, CompiledRelationLocation] = {}
    model_name: str
    relation: PhysicalRelationRecord
    for model_name, relation in physical_relations.items():
        model: CompiledModel | None = models_by_name.get(model_name)
        if model is None:
            raise PlannerInputError(
                f"checkpoint references unknown model '{model_name}'",
                code="S023",
            )
        targets_by_model[model_name] = build_virtual_destination_from_physical_relation(
            adapter=adapter,
            relation=relation,
            fallback_target=model.destination,
        )
    connection: Any = adapter.connect(connection_config)
    try:
        relation_lookup: RelationLookup = build_relation_lookup(
            adapter=adapter,
            connection=connection,
            locations=tuple(
                (target.database, target.schema, target.name)
                for target in targets_by_model.values()
            ),
        )
        for model_name, target in targets_by_model.items():
            if not relation_lookup.exists(
                database=target.database, schema=target.schema, name=target.name
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
            connection=state_connection,
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
    virtual_environment_name: str,
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
            target: CompiledRelationLocation = build_virtual_destination(
                adapter=adapter,
                target=function.destination,
                virtual_environment_name=virtual_environment_name,
            )
            adapter.ensure_schema(
                connection=connection,
                database=target.database,
                schema=target.schema,
                statement_recorder=recorder,
            )
            if target.qualified_name is None:
                continue
            adapter.create_function(
                connection=connection,
                definition=FunctionDefinition(
                    destination=target.qualified_name,
                    arguments=decode_function_arguments(record),
                    returns=record.returns,
                    body_sql=decode_function_body_sql(record),
                    return_columns=decode_function_return_columns(record),
                    language=decode_function_language(record),
                    runtime_version=record.runtime_version,
                    entry_point=record.entry_point,
                    packages=decode_function_packages(record),
                    source_file_path=None,
                ),
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)


def read_rollback_checkpoint_state(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    virtual_environment_name: str,
    checkpoint_id: str | None,
) -> RollbackCheckpointState:
    """Read current refs and resolve the rollback target checkpoint."""

    environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
        connection=state_connection,
        schema=schema,
        virtual_environment_name=virtual_environment_name,
    )
    if environment is not None and environment.status == VirtualEnvironmentStatus.DETACHED:
        raise PlannerInputError(
            f"virtual environment '{virtual_environment_name}' is detached",
            code="S028",
        )
    current_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
        backend.get_virtual_environment_model_refs(
            connection=state_connection,
            schema=schema,
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
            connection=state_connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
        )
    )
    target_checkpoint, target_checkpoint_model_refs = resolve_target_checkpoint(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        checkpoints=checkpoints,
        current_ref_map=current_ref_map,
        checkpoint_id=checkpoint_id,
    )
    if target_checkpoint is None:
        raise PlannerInputError(
            "no previous finalized checkpoint is available for rollback",
            code="S021",
        )
    target_checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...] = (
        backend.get_virtual_environment_checkpoint_function_refs(
            connection=state_connection,
            schema=schema,
            checkpoint_id=target_checkpoint.checkpoint_id,
        )
    )
    target_checkpoint_seed_refs: tuple[VirtualEnvironmentCheckpointSeedRefRecord, ...] = (
        backend.get_virtual_environment_checkpoint_seed_refs(
            connection=state_connection,
            schema=schema,
            checkpoint_id=target_checkpoint.checkpoint_id,
        )
    )
    return RollbackCheckpointState(
        current_ref_map=current_ref_map,
        target_checkpoint=target_checkpoint,
        checkpoint_model_refs=target_checkpoint_model_refs,
        checkpoint_function_refs=target_checkpoint_function_refs,
        checkpoint_seed_refs=target_checkpoint_seed_refs,
    )


def resolve_rollback_final_refs(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    graph: ProjectGraph,
    virtual_environment_name: str,
    checkpoint_state: RollbackCheckpointState,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    include_stale_upstreams: bool,
    allow_partial_rollback: bool,
) -> RollbackResolution:
    """Resolve final ref hashes, scope, and target status for the rollback."""

    selected_model_names: tuple[str, ...] = resolve_selected_model_names(
        graph=graph,
        select=select,
        exclude=exclude,
        all_model_names=tuple(model.name for model in graph.project.models),
        target_checkpoint_model_refs=checkpoint_state.checkpoint_model_refs,
    )
    checkpoint_ref_map: dict[str, str] = {
        ref.model_name: ref.version_hash for ref in checkpoint_state.checkpoint_model_refs
    }
    checkpoint_seed_ref_map: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in checkpoint_state.checkpoint_seed_refs
    }
    missing_checkpoint_model_refs: tuple[str, ...] = tuple(
        model_name for model_name in selected_model_names if model_name not in checkpoint_ref_map
    )
    if missing_checkpoint_model_refs:
        raise PlannerInputError(
            "checkpoint is missing selected refs: " + ", ".join(missing_checkpoint_model_refs),
            code="S025",
        )
    final_version_hashes: dict[str, str] = dict(checkpoint_state.current_ref_map)
    for model_name in selected_model_names:
        final_version_hashes[model_name] = checkpoint_ref_map[model_name]
    current_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = (
        backend.get_virtual_environment_seed_refs(
            connection=state_connection,
            schema=schema,
            virtual_environment_name=virtual_environment_name,
        )
    )
    final_seed_hashes: dict[str, str] = {
        ref.seed_name: ref.version_hash for ref in current_seed_refs
    }
    selected_seed_names: tuple[str, ...] = selected_upstream_seed_names(
        graph=graph,
        selected_model_names=selected_model_names,
        all_seed_names=tuple(seed.name for seed in graph.project.seeds),
        include_all=not bool(select or exclude),
    )
    missing_checkpoint_seed_refs: tuple[str, ...] = tuple(
        seed_name for seed_name in selected_seed_names if seed_name not in checkpoint_seed_ref_map
    )
    if missing_checkpoint_seed_refs:
        raise PlannerInputError(
            "checkpoint is missing selected seed refs: " + ", ".join(missing_checkpoint_seed_refs),
            code="S025",
        )
    for seed_name in selected_seed_names:
        final_seed_hashes[seed_name] = checkpoint_seed_ref_map[seed_name]
    stale_after: tuple[str, ...] = stale_after_rollback(
        graph=graph,
        final_version_hashes=final_version_hashes,
        expected_version_hashes=checkpoint_ref_map,
    )
    is_partial_scope: bool = bool(select or exclude)
    if is_partial_scope:
        selected_model_names, final_version_hashes = guard_partial_rollback_scope(
            graph=graph,
            selected_model_names=selected_model_names,
            stale_after=stale_after,
            checkpoint_ref_map=checkpoint_ref_map,
            final_version_hashes=final_version_hashes,
            include_stale_upstreams=include_stale_upstreams,
        )
        stale_after = stale_after_rollback(
            graph=graph,
            final_version_hashes=final_version_hashes,
            expected_version_hashes=checkpoint_ref_map,
        )
        if stale_after and not allow_partial_rollback:
            raise PlannerInputError(
                "rollback would leave target virtual environment working; "
                "remaining stale models: " + ", ".join(stale_after),
                code="S027",
                help="Re-run with --allow-partial-rollback to accept a working target VDE.",
            )
    status: VirtualEnvironmentStatus = (
        VirtualEnvironmentStatus.FINALIZED
        if not is_partial_scope or not stale_after
        else VirtualEnvironmentStatus.ACTIVE
    )
    rolled_back_model_names: tuple[str, ...] = tuple(
        sorted(
            model_name
            for model_name, version_hash in checkpoint_state.current_ref_map.items()
            if final_version_hashes.get(model_name) != version_hash
        )
    )
    return RollbackResolution(
        final_version_hashes=final_version_hashes,
        final_seed_hashes=final_seed_hashes,
        is_partial_scope=is_partial_scope,
        status=status,
        rolled_back_model_names=rolled_back_model_names,
    )


def read_rollback_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    checkpoint_id: str,
    resolution: RollbackResolution,
) -> VirtualEnvironmentPhysicalRelations:
    """Read tracked physical relations backing the rollback target refs."""

    model_relations: dict[str, PhysicalRelationRecord] = read_physical_relations(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        refs=tuple(
            VirtualEnvironmentCheckpointModelRefRecord(
                checkpoint_id=checkpoint_id,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in sorted(resolution.final_version_hashes.items())
        ),
    )
    seed_relations: dict[str, PhysicalRelationRecord] = read_seed_physical_relations(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        refs=tuple(
            VirtualEnvironmentCheckpointSeedRefRecord(
                checkpoint_id=checkpoint_id,
                seed_name=seed_name,
                version_hash=version_hash,
            )
            for seed_name, version_hash in sorted(resolution.final_seed_hashes.items())
        ),
    )
    return VirtualEnvironmentPhysicalRelations(
        model_relations=model_relations,
        seed_relations=seed_relations,
    )


def build_rollback_ref_update(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    virtual_environment_name: str,
    resolution: RollbackResolution,
    checkpoint_function_refs: tuple[VirtualEnvironmentCheckpointFunctionRefRecord, ...],
) -> RollbackRefUpdate:
    """Build the environment record and replacement ref groups for the rollback."""

    target_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = tuple(
        VirtualEnvironmentModelRefRecord(
            virtual_environment_name=virtual_environment_name,
            model_name=model_name,
            version_hash=version_hash,
        )
        for model_name, version_hash in sorted(resolution.final_version_hashes.items())
    )
    virtual_environment_record: VirtualEnvironmentRecord = VirtualEnvironmentRecord(
        virtual_environment_name=virtual_environment_name,
        status=resolution.status,
    )
    destination_seed_refs: tuple[VirtualEnvironmentSeedRefRecord, ...] = tuple(
        VirtualEnvironmentSeedRefRecord(
            virtual_environment_name=virtual_environment_name,
            seed_name=seed_name,
            version_hash=version_hash,
        )
        for seed_name, version_hash in sorted(resolution.final_seed_hashes.items())
    )
    function_versions: dict[str, FunctionVersionRecord] = read_function_versions(
        backend=backend,
        state_connection=state_connection,
        schema=schema,
        refs=checkpoint_function_refs,
    )
    target_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = tuple(
        VirtualEnvironmentFunctionRefRecord(
            virtual_environment_name=virtual_environment_name,
            node_type=("table_fn" if decode_function_return_columns(function_version) else "udf"),
            function_name=ref.function_name,
            version_hash=ref.version_hash,
        )
        for ref in checkpoint_function_refs
        if (function_version := function_versions.get(ref.function_name)) is not None
    )
    refs_by_node_type: dict[str, tuple[VirtualEnvironmentNodeRefRecord, ...]] = {
        "model": tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type="model",
                node_name=ref.model_name,
                version_hash=ref.version_hash,
            )
            for ref in target_refs
        ),
        "seed": tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type="seed",
                node_name=ref.seed_name,
                version_hash=ref.version_hash,
            )
            for ref in destination_seed_refs
        ),
    }
    if not resolution.is_partial_scope:
        refs_by_node_type["udf"] = tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in target_function_refs
            if ref.node_type == CompiledResourceType.UDF
        )
        refs_by_node_type["table_fn"] = tuple(
            VirtualEnvironmentNodeRefRecord(
                virtual_environment_name=ref.virtual_environment_name,
                node_type=ref.node_type,
                node_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in target_function_refs
            if ref.node_type == CompiledResourceType.TABLE_FN
        )
    return RollbackRefUpdate(
        virtual_environment_record=virtual_environment_record,
        refs=target_refs,
        seed_refs=destination_seed_refs,
        function_refs=target_function_refs,
        function_versions=function_versions,
        refs_by_node_type=refs_by_node_type,
    )
