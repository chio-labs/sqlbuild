"""Virtual rollback public entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.helpers.environment_views import write_virtual_environment_views
from sqlbuild.virtual.executor.helpers.project_context import resolve_virtual_project_context
from sqlbuild.virtual.executor.helpers.rollback import (
    build_rollback_ref_update,
    read_rollback_checkpoint_state,
    read_rollback_physical_relations,
    resolve_rollback_final_refs,
    validate_physical_relations_exist,
)
from sqlbuild.virtual.executor.helpers.state_operations import (
    acquire_virtual_environment_lease_or_raise,
)
from sqlbuild.virtual.executor.models import (
    RollbackCheckpointState,
    RollbackRefUpdate,
    RollbackResolution,
    VirtualEnvironmentPhysicalRelations,
    VirtualProjectContext,
    VirtualViewRefreshHooks,
)
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.locks.release_lock import release_state_lease
from sqlbuild.virtual.state.models import StateLockLease
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

    context: VirtualProjectContext = resolve_virtual_project_context(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
        on_progress=on_progress,
    )
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
        lease = acquire_virtual_environment_lease_or_raise(
            backend,
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            owner_prefix="rollback",
            locked_error_code="S019",
        )
        checkpoint_state: RollbackCheckpointState = read_rollback_checkpoint_state(
            backend,
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            checkpoint_id=checkpoint_id,
        )
        resolution: RollbackResolution = resolve_rollback_final_refs(
            backend,
            state_connection,
            schema=config.schema,
            graph=context.graph,
            virtual_environment_name=virtual_environment_name,
            checkpoint_state=checkpoint_state,
            select=select,
            exclude=exclude,
            include_stale_upstreams=include_stale_upstreams,
            allow_partial_rollback=allow_partial_rollback,
        )
        relations: VirtualEnvironmentPhysicalRelations = read_rollback_physical_relations(
            backend,
            state_connection,
            schema=config.schema,
            checkpoint_id=checkpoint_state.target_checkpoint.checkpoint_id,
            resolution=resolution,
        )
        validate_physical_relations_exist(
            adapter=adapter,
            connection_config=connection_config,
            models_by_name={model.name: model for model in context.graph.project.models},
            physical_relations=relations.model_relations,
        )
        update: RollbackRefUpdate = build_rollback_ref_update(
            backend,
            state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            resolution=resolution,
            checkpoint_function_refs=checkpoint_state.checkpoint_function_refs,
        )
        backend.upsert_virtual_environment_and_replace_node_ref_groups(
            state_connection,
            schema=config.schema,
            record=update.virtual_environment_record,
            refs_by_node_type=update.refs_by_node_type,
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    finally:
        if lease is not None:
            _ = release_state_lease(
                backend,
                state_connection,
                schema=config.schema,
                lease=lease,
            )
        backend.close(state_connection)
    write_virtual_environment_views(
        graph=context.graph,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=virtual_environment_name,
        unsuffixed_virtual_environment_name=context.unsuffixed_virtual_environment_name,
        relations=relations,
        function_versions=(update.function_versions if not resolution.is_partial_scope else {}),
        hooks=VirtualViewRefreshHooks(
            on_progress=on_progress,
            on_connection_start=on_connection_start,
            on_connection_complete=on_connection_complete,
            on_connection_error=on_connection_error,
        ),
    )
    return (
        checkpoint_state.target_checkpoint.checkpoint_id,
        resolution.rolled_back_model_names,
        resolution.status,
    )
