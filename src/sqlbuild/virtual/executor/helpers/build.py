"""Virtual-mode build entrypoint."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo, StatementRecorder
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledProject,
    CompiledRelationTarget,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.executor.build.models import BuildExecutionResult
from sqlbuild.executor.build.types import BuildStatus
from sqlbuild.executor.pipeline.main.run import run_build_pipeline
from sqlbuild.shared.helpers.naming import resolve_target_qualified_name
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.environments import resolve_environment_name
from sqlbuild.spec.models.project import SnapshotsConfig
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_rewritten_model_targets,
    build_virtual_target,
    relation_type_for_model,
    rewrite_project_model_targets,
)
from sqlbuild.virtual.executor.models import VirtualBuildExecutionHooks, VirtualBuildPipelineResult
from sqlbuild.virtual.planner.main.output import apply_virtual_plan_output
from sqlbuild.virtual.planner.main.selection import resolve_virtual_plan_model_selection
from sqlbuild.virtual.planner.main.semantics import (
    build_virtual_plan_semantics,
)
from sqlbuild.virtual.planner.models import VirtualPlanSemantics
from sqlbuild.virtual.shared.helpers.encoding import encode_state_text
from sqlbuild.virtual.state.main.checkpoints import create_finalized_virtual_environment_checkpoint
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import (
    ModelVersionRecord,
    PhysicalRelationRecord,
    StateBackendConfig,
    VirtualEnvironmentRecord,
    VirtualEnvironmentRefRecord,
)
from sqlbuild.virtual.state.types import ModelVersionStatus, VirtualEnvironmentStatus


def run_virtual_build(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    no_sql_validation: bool = False,
    defer_sources_to: str | None = None,
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    virtual_environment_name: str | None = None,
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    fail_fast: bool = False,
    allow_snapshot_schema_change: bool = False,
    concurrency: int | None = None,
    cli_vars: dict[str, object] | None = None,
    snapshots: SnapshotsConfig | None = None,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    on_plan_ready: Callable[[CompiledProject, PlanOutput], VirtualBuildExecutionHooks]
    | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> VirtualBuildPipelineResult:
    """Execute a virtual-mode build."""

    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    physical_environment_name: str | None = resolve_environment_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        selected_environment=None,
    )
    target_vde_name: str | None = virtual_environment_name or physical_environment_name
    if target_vde_name is None:
        target_vde_name = "default"

    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        bound_refs: tuple[VirtualEnvironmentRefRecord, ...] = _read_or_initialize_refs(
            backend=backend,
            state_connection=state_connection,
            config=config,
            target_vde_name=target_vde_name,
            baseline_vde_name=physical_environment_name,
        )
        bound_model_versions: dict[str, ModelVersionRecord | None] = _read_bound_model_versions(
            backend=backend,
            state_connection=state_connection,
            config=config,
            bound_refs=bound_refs,
        )
        semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=bound_refs,
            bound_model_versions=bound_model_versions,
        )
        selected_model_names: tuple[str, ...] = resolve_virtual_plan_model_selection(
            graph=graph,
            select=select,
            exclude=exclude,
            default_selection=semantics.default_selection,
            stale_model_names=semantics.stale_model_names,
            include_stale_upstreams=include_stale_upstreams,
            changes_only=changes_only,
        )
        effective_select: tuple[str, ...] = selected_model_names
        bound_physical_relations: dict[str, PhysicalRelationRecord] = _read_bound_relations(
            backend=backend,
            state_connection=state_connection,
            config=config,
            bound_version_hashes=semantics.bound_version_hashes,
        )
    finally:
        backend.close(state_connection)

    selected_model_version_hashes: dict[str, str] = {
        model_name: semantics.expected_version_hashes[model_name]
        for model_name in selected_model_names
        if model_name in semantics.expected_version_hashes
    }
    rewritten_targets: dict[str, CompiledRelationTarget] = build_rewritten_model_targets(
        project=graph.project,
        adapter=adapter,
        selected_model_version_hashes=selected_model_version_hashes,
        bound_physical_relations=bound_physical_relations,
    )
    rewritten_project: CompiledProject = rewrite_project_model_targets(
        project=graph.project,
        rewritten_targets=rewritten_targets,
    )
    deferred_relations: dict[str, RelationInfo] = {
        model_name: RelationInfo(
            database=relation.database_name,
            schema=relation.schema_name,
            name=relation.relation_name,
            relation_type=relation.relation_type,
        )
        for model_name, relation in bound_physical_relations.items()
    }

    if on_connection_start is not None:
        on_connection_start(1)
    connection_start: float = time.monotonic()
    try:
        planning_connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - connection_start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - connection_start)
    try:
        plan_output: PlanOutput = build_execution_plan(
            project=rewritten_project,
            adapter=adapter,
            connection=planning_connection,
            select=effective_select,
            exclude=(),
            cursor_overrides=cursor_overrides,
            full_refresh=full_refresh,
            auto_load_sources=auto_load_sources,
            reload_sources=reload_sources,
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            defer_sources_to=defer_sources_to,
            deferred_relations=deferred_relations,
            on_progress=on_progress,
        )
    finally:
        adapter.close(planning_connection)
    plan_output = apply_virtual_plan_output(
        plan_output=plan_output,
        environment_name=target_vde_name,
        semantics=semantics,
        selected_model_names=selected_model_names,
    )
    effective_concurrency: int = (
        concurrency if concurrency is not None else rewritten_project.settings.concurrency
    )
    hooks: VirtualBuildExecutionHooks = (
        on_plan_ready(rewritten_project, plan_output)
        if on_plan_ready is not None
        else VirtualBuildExecutionHooks()
    )
    result: BuildExecutionResult = run_build_pipeline(
        plan=plan_output,
        connection_config=connection_config,
        adapter=adapter,
        settings=rewritten_project.settings,
        snapshots=snapshots or SnapshotsConfig(),
        allow_snapshot_schema_change=allow_snapshot_schema_change,
        run_id=rewritten_project.run_id,
        run_tests=True,
        run_audits=True,
        fail_fast=fail_fast,
        max_concurrency=effective_concurrency,
        on_node_start=hooks.on_node_start,
        on_node_complete=hooks.on_node_complete,
        on_sub_progress=hooks.on_sub_progress,
        loader_functions=discovered_inputs.loader_functions,
        loader_is_reload=reload_sources,
        start_cursor_ts=start_cursor_ts,
        end_cursor_ts=end_cursor_ts,
        start_cursor_int=start_cursor_int,
        end_cursor_int=end_cursor_int,
    )
    if result.status == BuildStatus.SUCCESS:
        _persist_successful_virtual_build(
            project=graph.project,
            adapter=adapter,
            connection_config=connection_config,
            backend=backend,
            config=config,
            target_vde_name=target_vde_name,
            baseline_vde_name=physical_environment_name,
            bound_version_hashes=semantics.bound_version_hashes,
            plan_output=plan_output,
            expected_local_hashes=semantics.expected_local_hashes,
            expected_metadata_jsons=semantics.expected_metadata_jsons,
            expected_version_hashes=semantics.expected_version_hashes,
        )

    return VirtualBuildPipelineResult(
        project=rewritten_project,
        plan_output=plan_output,
        execution_result=result,
    )


def _read_or_initialize_refs(
    *,
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    target_vde_name: str,
    baseline_vde_name: str | None,
) -> tuple[VirtualEnvironmentRefRecord, ...]:
    refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
        state_connection,
        schema=config.schema,
        virtual_environment_name=target_vde_name,
    )
    if refs or baseline_vde_name is None or baseline_vde_name == target_vde_name:
        return refs
    baseline_refs: tuple[VirtualEnvironmentRefRecord, ...] = backend.get_virtual_environment_refs(
        state_connection,
        schema=config.schema,
        virtual_environment_name=baseline_vde_name,
    )
    return tuple(
        VirtualEnvironmentRefRecord(
            virtual_environment_name=target_vde_name,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in baseline_refs
    )


def _read_bound_model_versions(
    *,
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    bound_refs: tuple[VirtualEnvironmentRefRecord, ...],
) -> dict[str, ModelVersionRecord | None]:
    return {
        ref.model_name: backend.get_model_version(
            state_connection,
            schema=config.schema,
            model_name=ref.model_name,
            version_hash=ref.version_hash,
        )
        for ref in bound_refs
    }


def _read_bound_relations(
    *,
    backend: Any,
    state_connection: Any,
    config: StateBackendConfig,
    bound_version_hashes: dict[str, str],
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {}
    for model_name, version_hash in bound_version_hashes.items():
        relation: PhysicalRelationRecord | None = backend.get_physical_relation(
            state_connection,
            schema=config.schema,
            model_name=model_name,
            version_hash=version_hash,
        )
        if relation is not None:
            relations[model_name] = relation
    return relations


def _persist_successful_virtual_build(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    backend: Any,
    config: StateBackendConfig,
    target_vde_name: str,
    baseline_vde_name: str | None,
    bound_version_hashes: dict[str, str],
    plan_output: PlanOutput,
    expected_local_hashes: dict[str, str],
    expected_metadata_jsons: dict[str, str],
    expected_version_hashes: dict[str, str],
) -> None:
    final_version_hashes: dict[str, str] = dict(bound_version_hashes)
    model_entries_by_name: dict[str, Any] = {
        entry.name: entry for entry in plan_output.model_entries
    }
    for entry in plan_output.model_entries:
        final_version_hashes[entry.name] = expected_version_hashes[entry.name]

    stale_after_build: tuple[str, ...] = tuple(
        model.name
        for model in project.models
        if final_version_hashes.get(model.name) != expected_version_hashes.get(model.name)
    )
    status: VirtualEnvironmentStatus = (
        VirtualEnvironmentStatus.FINALIZED
        if not stale_after_build
        else VirtualEnvironmentStatus.ACTIVE
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        model: CompiledModel
        for model in project.models:
            version_hash: str | None = final_version_hashes.get(model.name)
            if version_hash is None:
                continue
            entry: Any | None = model_entries_by_name.get(model.name)
            existing_model_version: ModelVersionRecord | None = backend.get_model_version(
                state_connection,
                schema=config.schema,
                model_name=model.name,
                version_hash=version_hash,
            )
            if existing_model_version is None:
                metadata_json: str = expected_metadata_jsons.get(model.name, "{}")
                backend.upsert_model_version(
                    state_connection,
                    schema=config.schema,
                    record=ModelVersionRecord(
                        model_name=model.name,
                        version_hash=version_hash,
                        data_hash=expected_local_hashes.get(model.name, version_hash),
                        metadata_hash=hashlib.sha256(metadata_json.encode("utf-8")).hexdigest(),
                        status=ModelVersionStatus.READY,
                        fingerprint_query_sql_b64=encode_state_text(model.query_sql),
                        fingerprint_metadata_json_b64=encode_state_text(metadata_json),
                        compiled_sql_b64=(
                            encode_state_text(entry.resolved_sql) if entry is not None else None
                        ),
                    ),
                )
            target: CompiledRelationTarget | None = entry.target if entry is not None else None
            if target is not None:
                existing_physical_relation: PhysicalRelationRecord | None = (
                    backend.get_physical_relation(
                        state_connection,
                        schema=config.schema,
                        model_name=model.name,
                        version_hash=version_hash,
                    )
                )
                if existing_physical_relation is None:
                    backend.upsert_physical_relation(
                        state_connection,
                        schema=config.schema,
                        record=PhysicalRelationRecord(
                            model_name=model.name,
                            version_hash=version_hash,
                            database_name=target.database,
                            schema_name=target.schema or "",
                            relation_name=target.name,
                            relation_type=relation_type_for_model(
                                str(model.config.values.get("materialized", "table"))
                            ),
                        ),
                    )
        backend.upsert_virtual_environment(
            state_connection,
            schema=config.schema,
            record=VirtualEnvironmentRecord(
                virtual_environment_name=target_vde_name,
                status=status,
                baseline_virtual_environment_name=(
                    baseline_vde_name if baseline_vde_name != target_vde_name else None
                ),
            ),
        )
        refs: tuple[VirtualEnvironmentRefRecord, ...] = tuple(
            VirtualEnvironmentRefRecord(
                virtual_environment_name=target_vde_name,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in sorted(final_version_hashes.items())
        )
        backend.replace_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=target_vde_name,
            refs=refs,
        )
        if status == VirtualEnvironmentStatus.FINALIZED and refs:
            create_finalized_virtual_environment_checkpoint(
                backend,
                state_connection,
                schema=config.schema,
                virtual_environment_name=target_vde_name,
                refs=refs,
            )
    finally:
        backend.close(state_connection)

    _create_logical_vde_views(
        project=project,
        adapter=adapter,
        connection_config=connection_config,
        target_vde_name=target_vde_name,
        plan_output=plan_output,
        final_version_hashes=final_version_hashes,
    )


def _create_logical_vde_views(
    *,
    project: CompiledProject,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    target_vde_name: str,
    plan_output: PlanOutput,
    final_version_hashes: dict[str, str],
) -> None:
    physical_targets: dict[str, CompiledRelationTarget] = {
        model.name: plan_output.model_targets.get(model.name, model.target)
        for model in project.models
    }
    connection: Any = adapter.connect(connection_config)
    recorder: StatementRecorder = StatementRecorder()
    try:
        model: CompiledModel
        for model in project.models:
            if model.name not in final_version_hashes:
                continue
            physical_target: CompiledRelationTarget | None = physical_targets.get(model.name)
            if physical_target is None:
                continue
            virtual_target: CompiledRelationTarget = build_virtual_target(
                adapter=adapter,
                target=model.target,
                virtual_environment_name=target_vde_name,
            )
            adapter.ensure_schema(
                connection,
                database=virtual_target.database,
                schema=virtual_target.schema,
                statement_recorder=recorder,
            )
            adapter.create_view_as(
                connection,
                target=resolve_target_qualified_name(adapter=adapter, target=virtual_target),
                sql=(
                    "SELECT * FROM "
                    + resolve_target_qualified_name(adapter=adapter, target=physical_target)
                ),
                statement_recorder=recorder,
            )
    finally:
        adapter.close(connection)
