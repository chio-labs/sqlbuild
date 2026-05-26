"""Virtual promote public entrypoint."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.virtual.executor.main.views import refresh_logical_vde_views
from sqlbuild.virtual.planner.main.selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main.semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.main.upstreams import build_virtual_stale_required_upstream_closure
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.state.main.locks import (
    acquire_virtual_environment_lease,
)
from sqlbuild.virtual.state.main.release_lock import release_state_lease
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    StateLockLease,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import VirtualEnvironmentStatus


def run_virtual_promote(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    from_virtual_environment_name: str,
    to_virtual_environment_name: str,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    allow_partial_promotion: bool = False,
    include_stale_upstreams: bool = False,
    no_sql_validation: bool = False,
    cli_vars: dict[str, object] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    on_progress: Callable[[str], None] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    """Promote refs from one VDE to another and refresh target views."""

    if on_progress is not None:
        on_progress("Compiling project...")
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    if on_progress is not None:
        on_progress("Compiled project.")
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    lease: StateLockLease | None = None
    try:
        if on_progress is not None:
            on_progress("Inspecting virtual state...")
        lease = acquire_virtual_environment_lease(
            backend,
            state_connection,
            schema=config.schema,
            virtual_environment_name=to_virtual_environment_name,
            owner_id=f"promote:{uuid.uuid4()}",
            ttl=timedelta(minutes=10),
        )
        if lease is None:
            raise PlannerInputError(
                f"virtual environment '{to_virtual_environment_name}' is locked",
                code="S014",
            )
        source_refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=from_virtual_environment_name,
        )
        target_refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=to_virtual_environment_name,
        )
        if not source_refs:
            raise PlannerInputError(
                f"unknown source virtual environment '{from_virtual_environment_name}'",
                code="S011",
            )
        source_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=source_refs,
        )
        target_versions: dict[str, ModelVersionRecord | None] = _read_model_versions(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=target_refs,
        )
        source_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=source_refs,
            bound_model_versions=source_versions,
        )
        target_semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=target_refs,
            bound_model_versions=target_versions,
        )
        selected_model_names: tuple[str, ...] = resolve_virtual_plan_model_selection(
            graph=graph,
            select=select,
            exclude=exclude,
            default_selection=tuple(model.name for model in graph.project.models),
            stale_model_names=source_semantics.stale_model_names,
            include_stale_upstreams=include_stale_upstreams,
            changes_only=False,
        )
        if not select:
            selected_model_names = tuple(model.name for model in graph.project.models)
        source_ref_map: dict[str, str] = {ref.model_name: ref.version_hash for ref in source_refs}
        missing_source_refs: tuple[str, ...] = tuple(
            model_name for model_name in selected_model_names if model_name not in source_ref_map
        )
        if missing_source_refs:
            raise PlannerInputError(
                "source virtual environment is missing selected refs: "
                + ", ".join(missing_source_refs),
                code="S015",
            )
        final_version_hashes: dict[str, str] = {
            ref.model_name: ref.version_hash for ref in target_refs
        }
        for model_name in selected_model_names:
            final_version_hashes[model_name] = source_ref_map[model_name]
        stale_after: tuple[str, ...] = tuple(
            model.name
            for model in graph.project.models
            if final_version_hashes.get(model.name)
            != target_semantics.expected_version_hashes.get(model.name)
        )
        stale_upstreams: tuple[str, ...] = build_virtual_stale_required_upstream_closure(
            graph=graph,
            selected_model_names=selected_model_names,
            stale_model_names=stale_after,
        )
        if stale_upstreams and not include_stale_upstreams:
            raise PlannerInputError(
                "selected promotion scope is missing stale required upstream models: "
                + ", ".join(stale_upstreams),
                code="S016",
                help="Re-run with --include-stale-upstreams to add required upstream refs.",
            )
        if stale_upstreams:
            selected_model_names = tuple(sorted({*selected_model_names, *stale_upstreams}))
            for model_name in stale_upstreams:
                final_version_hashes[model_name] = source_ref_map[model_name]
            stale_after = tuple(
                model.name
                for model in graph.project.models
                if final_version_hashes.get(model.name)
                != target_semantics.expected_version_hashes.get(model.name)
            )
        if stale_after and not allow_partial_promotion:
            raise PlannerInputError(
                "promotion would leave target virtual environment working; remaining stale models: "
                + ", ".join(stale_after),
                code="S017",
                help="Re-run with --allow-partial-promotion to accept a working target VDE.",
            )
        status: VirtualEnvironmentStatus = (
            VirtualEnvironmentStatus.FINALIZED
            if not stale_after
            else VirtualEnvironmentStatus.ACTIVE
        )
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=to_virtual_environment_name,
                status=status,
                baseline_virtual_environment_name=from_virtual_environment_name,
            ),
        )
        refs: tuple[VirtualEnvironmentRefRecord, ...] = tuple(
            VirtualEnvironmentRefRecord(
                virtual_environment_name=to_virtual_environment_name,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in sorted(final_version_hashes.items())
        )
        backend.replace_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=to_virtual_environment_name,
            refs=refs,
        )
        physical_relations: dict[str, PhysicalRelationRecord] = _read_physical_relations(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            refs=refs,
        )
        if on_progress is not None:
            on_progress("Inspected virtual state.")
    finally:
        if lease is not None:
            release_state_lease(
                backend,
                state_connection,
                schema=config.schema,
                lease=lease,
            )
        backend.close(state_connection)

    if on_progress is not None:
        on_progress("Refreshing target VDE views...")
    refresh_logical_vde_views(
        project=graph.project,
        adapter=adapter,
        connection_config=connection_config,
        virtual_environment_name=to_virtual_environment_name,
        physical_relations=physical_relations,
        on_connection_start=on_connection_start,
        on_connection_complete=on_connection_complete,
        on_connection_error=on_connection_error,
    )
    if on_progress is not None:
        on_progress("Refreshed target VDE views.")
    return status.value, selected_model_names, stale_after


def _read_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentRefRecord, ...],
) -> dict[str, ModelVersionRecord | None]:
    return {
        ref.model_name: backend.get_model_version(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in refs
    }


def _read_physical_relations(
    *,
    backend: Any,
    state_connection: Any,
    schema: str,
    refs: tuple[VirtualEnvironmentRefRecord, ...],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    for ref in refs:
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            state_connection,
            schema=schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        if relation is not None:
            relations[ref.model_name] = relation
    return relations
