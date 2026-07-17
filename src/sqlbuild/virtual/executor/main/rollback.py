"""Virtual rollback public entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.virtual.executor._helpers.environment_views import write_virtual_environment_views
from sqlbuild.virtual.executor._helpers.project_context import resolve_virtual_project_context
from sqlbuild.virtual.executor._helpers.rollback import (
    build_rollback_ref_update,
    read_rollback_checkpoint_state,
    read_rollback_physical_relations,
    resolve_rollback_final_refs,
    validate_physical_relations_exist,
)
from sqlbuild.virtual.executor._helpers.state_operations import (
    acquire_virtual_environment_lease_or_raise,
)
from sqlbuild.virtual.executor.models import (
    RollbackCheckpointState,
    RollbackOptions,
    RollbackRefUpdate,
    RollbackResolution,
    VirtualEnvironmentPhysicalRelations,
    VirtualProjectContext,
)
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.locks._release_lock import release_state_lease
from sqlbuild.virtual.state.models import StateLockLease
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def run_virtual_rollback(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    virtual_environment_name: str,
    options: RollbackOptions,
    hooks: ConnectionHooks,
) -> tuple[str, tuple[str, ...], VirtualEnvironmentStatus]:
    """Rollback a VDE to the previous finalized checkpoint."""

    on_progress: Callable[[str], None] | None = hooks.on_progress
    context: VirtualProjectContext = resolve_virtual_project_context(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=options.no_sql_validation,
        cli_vars=options.cli_vars,
        external_sql_reference_resolver=options.external_sql_reference_resolver,
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
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            owner_prefix="rollback",
            locked_error_code="S019",
        )
        checkpoint_state: RollbackCheckpointState = read_rollback_checkpoint_state(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            checkpoint_id=options.checkpoint_id,
        )
        resolution: RollbackResolution = resolve_rollback_final_refs(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            graph=context.graph,
            virtual_environment_name=virtual_environment_name,
            checkpoint_state=checkpoint_state,
            select=options.select,
            exclude=options.exclude,
            include_stale_upstreams=options.include_stale_upstreams,
            allow_partial_rollback=options.allow_partial_rollback,
        )
        relations: VirtualEnvironmentPhysicalRelations = read_rollback_physical_relations(
            backend=backend,
            state_connection=state_connection,
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
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            virtual_environment_name=virtual_environment_name,
            resolution=resolution,
            checkpoint_function_refs=checkpoint_state.checkpoint_function_refs,
        )
        backend.upsert_virtual_environment_and_replace_node_ref_groups(
            connection=state_connection,
            schema=config.schema,
            record=update.virtual_environment_record,
            refs_by_node_type=update.refs_by_node_type,
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    finally:
        if lease is not None:
            _ = release_state_lease(
                backend=backend,
                connection=state_connection,
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
        hooks=hooks,
    )
    return (
        checkpoint_state.target_checkpoint.checkpoint_id,
        resolution.rolled_back_model_names,
        resolution.status,
    )
