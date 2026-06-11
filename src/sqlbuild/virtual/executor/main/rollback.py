"""Virtual rollback public entrypoint."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledModel
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.targets import resolve_target_config, resolve_target_name
from sqlbuild.virtual.executor.helpers.rollback import (
    guard_partial_rollback_scope,
    publish_function_versions,
    read_function_versions,
    read_physical_relations,
    resolve_selected_model_names,
    resolve_target_checkpoint,
    stale_after_rollback,
    validate_physical_relations_exist,
)
from sqlbuild.virtual.executor.main.views import refresh_logical_vde_views
from sqlbuild.virtual.state.main.locks import acquire_virtual_environment_lease
from sqlbuild.virtual.state.main.release_lock import release_state_lease
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    FunctionVersionRecord,
    PhysicalRelationRecord,
    StateLockLease,
    VirtualEnvironmentCheckpointFunctionRefRecord,
    VirtualEnvironmentCheckpointModelRefRecord,
    VirtualEnvironmentCheckpointRecord,
    VirtualEnvironmentFunctionRefRecord,
    VirtualEnvironmentModelRefRecord,
    VirtualEnvironmentRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def run_virtual_rollback(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    checkpoint_id: str | None = None,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    allow_partial_rollback: bool = False,
    include_stale_upstreams: bool = False,
    no_sql_validation: bool = False,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
) -> tuple[str, tuple[str, ...], VirtualEnvironmentStatus]:
    """Rollback a VDE to the previous finalized checkpoint."""

    compile_start: float = time.perf_counter()
    if on_progress is not None:
        on_progress("Compiling project...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    active_target_name: str | None = resolve_target_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_target=None,
    )
    unsuffixed_virtual_environment_name: str | None = None
    if active_target_name is not None:
        unsuffixed_virtual_environment_name = resolve_target_config(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            target_name=active_target_name,
        ).state.unsuffixed_virtual_env
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.perf_counter() - compile_start:.2f}s)")
    models_by_name: dict[str, CompiledModel] = {model.name: model for model in graph.project.models}
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    lease: StateLockLease | None = None
    try:
        inspect_start: float = time.perf_counter()
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
        environment: VirtualEnvironmentRecord | None = backend.get_virtual_environment(
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
        )
        if environment is not None and environment.status == VirtualEnvironmentStatus.DETACHED:
            raise PlannerInputError(
                f"virtual environment '{virtual_environment_name}' is detached",
                code="S028",
            )
        current_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = (
            backend.get_virtual_environment_model_refs(
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
        target_checkpoint, target_checkpoint_model_refs = resolve_target_checkpoint(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            checkpoints=checkpoints,
            current_ref_map=current_ref_map,
            checkpoint_id=checkpoint_id,
        )
        if target_checkpoint is None:
            raise PlannerInputError(
                "no previous finalized checkpoint is available for rollback",
                code="S021",
            )
        target_checkpoint_function_refs: tuple[
            VirtualEnvironmentCheckpointFunctionRefRecord, ...
        ] = backend.get_virtual_environment_checkpoint_function_refs(
            state_connection,
            schema=config.schema,
            checkpoint_id=target_checkpoint.checkpoint_id,
        )
        selected_model_names: tuple[str, ...] = resolve_selected_model_names(
            graph=graph,
            select=select,
            exclude=exclude,
            all_model_names=tuple(model.name for model in graph.project.models),
            target_checkpoint_model_refs=target_checkpoint_model_refs,
        )
        checkpoint_ref_map: dict[str, str] = {
            ref.model_name: ref.version_hash for ref in target_checkpoint_model_refs
        }
        missing_checkpoint_model_refs: tuple[str, ...] = tuple(
            model_name
            for model_name in selected_model_names
            if model_name not in checkpoint_ref_map
        )
        if missing_checkpoint_model_refs:
            raise PlannerInputError(
                "checkpoint is missing selected refs: " + ", ".join(missing_checkpoint_model_refs),
                code="S025",
            )
        final_version_hashes: dict[str, str] = dict(current_ref_map)
        for model_name in selected_model_names:
            final_version_hashes[model_name] = checkpoint_ref_map[model_name]
        stale_after: tuple[str, ...] = stale_after_rollback(
            graph=graph,
            final_version_hashes=final_version_hashes,
            expected_version_hashes=checkpoint_ref_map,
        )
        is_partial_scope: bool = bool(select or exclude)
        if is_partial_scope:
            selected_model_names = guard_partial_rollback_scope(
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
        physical_relations: dict[str, PhysicalRelationRecord] = read_physical_relations(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=tuple(
                VirtualEnvironmentCheckpointModelRefRecord(
                    checkpoint_id=target_checkpoint.checkpoint_id,
                    model_name=model_name,
                    version_hash=version_hash,
                )
                for model_name, version_hash in sorted(final_version_hashes.items())
            ),
        )
        validate_physical_relations_exist(
            adapter=adapter,
            connection_config=connection_config,
            models_by_name=models_by_name,
            physical_relations=physical_relations,
        )
        target_refs: tuple[VirtualEnvironmentModelRefRecord, ...] = tuple(
            VirtualEnvironmentModelRefRecord(
                virtual_environment_name=virtual_environment_name,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in sorted(final_version_hashes.items())
        )
        status: VirtualEnvironmentStatus = (
            VirtualEnvironmentStatus.FINALIZED
            if not is_partial_scope or not stale_after
            else VirtualEnvironmentStatus.ACTIVE
        )
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=virtual_environment_name,
                status=status,
            ),
        )
        backend.replace_virtual_environment_model_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            refs=target_refs,
        )
        target_function_refs: tuple[VirtualEnvironmentFunctionRefRecord, ...] = tuple(
            VirtualEnvironmentFunctionRefRecord(
                virtual_environment_name=virtual_environment_name,
                function_name=ref.function_name,
                version_hash=ref.version_hash,
            )
            for ref in target_checkpoint_function_refs
        )
        function_versions: dict[str, FunctionVersionRecord] = read_function_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=target_checkpoint_function_refs,
        )
        if not is_partial_scope:
            backend.replace_virtual_environment_function_refs(
                state_connection,
                schema=config.schema,
                virtual_environment_name=virtual_environment_name,
                refs=target_function_refs,
            )
        rolled_back_models: tuple[str, ...] = tuple(
            sorted(
                model_name
                for model_name, version_hash in current_ref_map.items()
                if final_version_hashes.get(model_name) != version_hash
            )
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    finally:
        if lease is not None:
            release_state_lease(
                backend,
                state_connection,
                schema=config.schema,
                lease=lease,
            )
        backend.close(state_connection)

    refresh_start: float = time.perf_counter()
    if on_progress is not None:
        on_progress("Refreshing target VDE views...")
    refresh_logical_vde_views(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=unsuffixed_virtual_environment_name,
        physical_relations=physical_relations,
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
    )
    if function_versions and not is_partial_scope:
        publish_function_versions(
            adapter=adapter,
            connection_config=connection_config,
            graph=graph,
            virtual_environment_name=virtual_environment_name,
            function_versions=function_versions,
        )
    if on_progress is not None:
        on_progress(f"Refreshed target VDE views. ({time.perf_counter() - refresh_start:.2f}s)")
    return target_checkpoint.checkpoint_id, rolled_back_models, status
