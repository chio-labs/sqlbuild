"""Virtual promote public entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.shared.models import ConnectionHooks
from sqlbuild.virtual.executor.helpers.environment_views import write_virtual_environment_views
from sqlbuild.virtual.executor.helpers.project_context import resolve_virtual_project_context
from sqlbuild.virtual.executor.helpers.promote import (
    build_promote_ref_update,
    build_promote_semantics,
    read_promote_environment_state,
    read_promote_physical_relations,
    resolve_promote_final_refs,
    resolve_promote_selection,
    write_promote_environment_update,
)
from sqlbuild.virtual.executor.helpers.state_operations import (
    acquire_virtual_environment_lease_or_raise,
    create_state_operation_handle,
    write_state_operation_result,
    write_state_operation_started,
)
from sqlbuild.virtual.executor.models import (
    PromoteEnvironmentState,
    PromoteOptions,
    PromoteRefUpdate,
    PromoteResolution,
    PromoteSelection,
    PromoteSemantics,
    StateOperationHandle,
    VirtualEnvironmentPhysicalRelations,
    VirtualProjectContext,
)
from sqlbuild.virtual.state.main.environments.runtime import build_state_runtime
from sqlbuild.virtual.state.main.locks.release_lock import release_state_lease
from sqlbuild.virtual.state.models import StateLockLease
from sqlbuild.virtual.state.types import StateOperationStatus, StateOperationType


def run_virtual_promote(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    options: PromoteOptions,
    hooks: ConnectionHooks,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Promote refs from one VDE to another and refresh target views."""

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
    handle: StateOperationHandle = create_state_operation_handle(StateOperationType.PROMOTE)
    try:
        inspect_start: float = time.perf_counter()
        if on_progress is not None:
            on_progress("Inspecting virtual state...")
        write_state_operation_started(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            handle=handle,
            virtual_environment_name=to_virtual_environment_name,
            message=(
                f"promote from {from_virtual_environment_name} to {to_virtual_environment_name}"
            ),
        )
        lease = acquire_virtual_environment_lease_or_raise(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            virtual_environment_name=to_virtual_environment_name,
            owner_prefix="promote",
            locked_error_code="S014",
        )
        environment_state: PromoteEnvironmentState = read_promote_environment_state(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            from_virtual_environment_name=from_virtual_environment_name,
            to_virtual_environment_name=to_virtual_environment_name,
        )
        semantics: PromoteSemantics = build_promote_semantics(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            graph=context.graph,
            environment_state=environment_state,
        )
        selection: PromoteSelection = resolve_promote_selection(
            graph=context.graph,
            environment_state=environment_state,
            source_semantics=semantics.source,
            select=options.select,
            exclude=options.exclude,
            include_stale_upstreams=options.include_stale_upstreams,
        )
        resolution: PromoteResolution = resolve_promote_final_refs(
            graph=context.graph,
            environment_state=environment_state,
            selection=selection,
            target_semantics=semantics.target,
            select=options.select,
            include_stale_upstreams=options.include_stale_upstreams,
            allow_partial_promotion=options.allow_partial_promotion,
        )
        update: PromoteRefUpdate = build_promote_ref_update(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            from_virtual_environment_name=from_virtual_environment_name,
            to_virtual_environment_name=to_virtual_environment_name,
            resolution=resolution,
            source_function_refs=environment_state.source_function_refs,
            select=options.select,
        )
        write_promote_environment_update(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            to_virtual_environment_name=to_virtual_environment_name,
            update=update,
        )
        relations: VirtualEnvironmentPhysicalRelations = read_promote_physical_relations(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            update=update,
        )
        write_virtual_environment_views(
            graph=context.graph,
            adapter=adapter,
            connection_config=connection_config,
            virtual_environment_name=to_virtual_environment_name,
            unsuffixed_virtual_environment_name=context.unsuffixed_virtual_environment_name,
            relations=relations,
            function_versions=update.function_versions,
            hooks=hooks,
        )
        write_state_operation_result(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            handle=handle,
            status=StateOperationStatus.SUCCEEDED,
            message=f"promoted {resolution.promoted_model_count} models",
        )
        if on_progress is not None:
            on_progress(f"Inspected virtual state. ({time.perf_counter() - inspect_start:.2f}s)")
    except Exception as error:
        write_state_operation_result(
            backend,
            state_connection=state_connection,
            schema=config.schema,
            handle=handle,
            status=StateOperationStatus.FAILED,
            message=f"{error}",
        )
        raise
    finally:
        if lease is not None:
            _ = release_state_lease(
                backend,
                connection=state_connection,
                schema=config.schema,
                lease=lease,
            )
        backend.close(state_connection)
    return resolution.status.value, resolution.selected_model_names, resolution.stale_after
