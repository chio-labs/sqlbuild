"""Virtual-mode planning entrypoint."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import CompiledRelationTarget
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import CompilePipelineResult, ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.planner.types import PlanReason
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.environments import resolve_environment_name
from sqlbuild.virtual.planner.helpers.output import (
    rewrite_virtual_plan_entries,
    with_virtual_metadata,
)
from sqlbuild.virtual.planner.helpers.planning import (
    build_bound_local_hashes,
    build_bound_version_hashes,
    build_default_virtual_selection,
    build_expected_local_hashes,
    build_expected_version_hashes,
    build_model_fingerprint_metadata_jsons,
    build_stale_model_names,
    build_stale_root_cause_reasons,
    build_stale_root_causes,
    build_stale_root_reasons,
    build_stale_root_source_causes,
    resolve_virtual_model_selection,
)
from sqlbuild.virtual.planner.helpers.state_metadata import (
    decode_model_version_metadata_jsons,
    decode_model_version_query_sqls,
    read_previous_function_query_sqls,
)
from sqlbuild.virtual.planner.helpers.targets import build_target_from_physical_relation
from sqlbuild.virtual.state.main.runtime import build_state_runtime
from sqlbuild.virtual.state.models import ModelVersionRecord, PhysicalRelationRecord


def run_virtual_plan_pipeline(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    no_sql_validation: bool = False,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    virtual_environment_name: str | None = None,
    include_stale_upstreams: bool = False,
    changes_only: bool = False,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    connection_config: dict[str, object] | None = None,
    cli_vars: dict[str, object] | None = None,
    on_connection_start: Callable[[int], None] | None = None,
    on_connection_complete: Callable[[int, float], None] | None = None,
    on_connection_error: Callable[[int, float], None] | None = None,
    on_progress: Callable[[str], None] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
) -> CompilePipelineResult:
    """Run the planner-only virtual pipeline for `sqb plan`."""

    if connection_config is None:
        raise PlannerInputError("virtual planning requires explicit connection_config")
    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(connection_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
    try:
        graph: ProjectGraph = build_project_graph(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            no_sql_validation=no_sql_validation,
            cli_vars=cli_vars,
            external_sql_reference_resolver=external_sql_reference_resolver,
        )
        expected_local_hashes: dict[str, str] = build_expected_local_hashes(
            graph=graph,
        )
        expected_version_hashes: dict[str, str] = build_expected_version_hashes(
            graph=graph,
            expected_local_hashes=expected_local_hashes,
        )
        expected_metadata_jsons: dict[str, str] = build_model_fingerprint_metadata_jsons(
            graph=graph
        )
        (
            bound_version_hashes,
            bound_local_hashes,
            deferred_targets,
            deferred_relations,
            previous_query_sqls,
            previous_metadata_jsons,
            previous_function_query_sqls,
        ) = _read_bound_state(
            discovered_inputs=discovered_inputs,
            project_dir=project_dir,
            adapter=adapter,
            graph=graph,
            virtual_environment_name=virtual_environment_name,
        )
        stale_model_names: tuple[str, ...] = build_stale_model_names(
            model_names=tuple(model.name for model in graph.project.models),
            expected_version_hashes=expected_version_hashes,
            bound_version_hashes=bound_version_hashes,
        )
        stale_root_reasons: dict[str, PlanReason] = build_stale_root_reasons(
            stale_model_names=stale_model_names,
            expected_local_hashes=expected_local_hashes,
            bound_version_hashes=bound_version_hashes,
            bound_local_hashes=bound_local_hashes,
            current_query_sqls={model.name: model.query_sql for model in graph.project.models},
            bound_previous_query_sqls=previous_query_sqls,
            expected_metadata_jsons=expected_metadata_jsons,
            bound_metadata_jsons=previous_metadata_jsons,
        )
        stale_root_source_causes: dict[str, str] = build_stale_root_source_causes(
            stale_root_reasons=stale_root_reasons,
            expected_metadata_jsons=expected_metadata_jsons,
            bound_metadata_jsons=previous_metadata_jsons,
        )
        stale_root_causes: dict[str, str] = build_stale_root_causes(
            stale_model_names=stale_model_names,
            stale_root_reasons=stale_root_reasons,
            graph=graph,
            stale_root_source_causes=stale_root_source_causes,
        )
        stale_root_cause_reasons: dict[str, PlanReason] = build_stale_root_cause_reasons(
            stale_root_reasons=stale_root_reasons,
            stale_root_source_causes=stale_root_source_causes,
        )
        default_selection: tuple[str, ...] = build_default_virtual_selection(
            stale_model_names=stale_model_names,
            graph=graph,
        )
        effective_select: tuple[str, ...] = resolve_virtual_model_selection(
            graph=graph,
            select=select,
            exclude=exclude,
            default_selection=default_selection,
            stale_model_names=stale_model_names,
            include_stale_upstreams=include_stale_upstreams,
            changes_only=changes_only,
        )

        if effective_select:
            plan_output: PlanOutput = build_execution_plan(
                project=graph.project,
                adapter=adapter,
                connection=connection,
                select=effective_select,
                exclude=(),
                cursor_overrides=cursor_overrides,
                full_refresh=full_refresh,
                auto_load_sources=auto_load_sources,
                reload_sources=reload_sources,
                on_progress=on_progress,
                project_config=discovered_inputs.project_config,
                local_config=discovered_inputs.local_config,
                defer_sources_to=defer_sources_to,
                source_deferral_enabled=source_deferral_enabled,
                deferred_targets=deferred_targets,
                deferred_relations=deferred_relations,
            )
        else:
            plan_output = PlanOutput(
                execution_order=tuple(graph.upstream_deps),
                upstream_deps=graph.upstream_deps,
                downstream_deps=graph.downstream_deps,
                model_targets={model.name: model.target for model in graph.project.models},
                function_targets={
                    function.name: function.target for function in graph.project.functions
                },
                seed_targets={seed.name: seed.target for seed in graph.project.seeds},
                source_map={source.name: source.source_entry for source in graph.project.sources},
            )
        plan_output = rewrite_virtual_plan_entries(
            plan_output=plan_output,
            stale_root_reasons=stale_root_reasons,
            stale_root_causes=stale_root_causes,
            stale_root_cause_reasons=stale_root_cause_reasons,
            previous_query_sqls=previous_query_sqls,
            current_metadata_jsons=expected_metadata_jsons,
            previous_metadata_jsons=previous_metadata_jsons,
            previous_function_query_sqls=previous_function_query_sqls,
        )
        plan_output = with_virtual_metadata(
            plan_output=plan_output,
            environment_name=_resolve_virtual_environment_name(
                physical_environment_name=graph.project.effective_environment_name,
                virtual_environment_name=virtual_environment_name,
            ),
            stale_model_names=stale_model_names,
            stale_root_names=tuple(sorted(stale_root_reasons)),
            remaining_stale_model_names=tuple(
                sorted(set(stale_model_names) - set(effective_select))
            ),
        )
        return CompilePipelineResult(
            project=graph.project,
            plan_output=plan_output,
        )
    finally:
        adapter.close(connection)


def _read_bound_state(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    project_dir: Path,
    adapter: BaseAdapter,
    graph: ProjectGraph,
    virtual_environment_name: str | None,
) -> tuple[
    dict[str, str],
    dict[str, str],
    dict[str, CompiledRelationTarget],
    dict[str, RelationInfo],
    dict[str, str],
    dict[str, str],
    dict[str, str],
]:
    config, backend = build_state_runtime(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )
    state_connection: Any = backend.connect(config.connection)
    try:
        physical_environment_name: str | None = resolve_environment_name(
            project_config=discovered_inputs.project_config,
            local_config=discovered_inputs.local_config,
            selected_environment=None,
        )
        environment_name: str | None = _resolve_virtual_environment_name(
            physical_environment_name=physical_environment_name,
            virtual_environment_name=virtual_environment_name,
        )
        if environment_name is None:
            return {}, {}, {}, {}, {}, {}, {}
        refs: tuple[object, ...] = backend.get_virtual_environment_refs(
            state_connection,
            schema=config.schema,
            virtual_environment_name=environment_name,
        )
        bound_version_hashes: dict[str, str] = build_bound_version_hashes(refs)
        model_versions: dict[str, ModelVersionRecord | None] = {
            model_name: backend.get_model_version(
                state_connection,
                schema=config.schema,
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in bound_version_hashes.items()
        }
        previous_query_sqls: dict[str, str] = decode_model_version_query_sqls(model_versions)
        previous_metadata_jsons: dict[str, str] = decode_model_version_metadata_jsons(
            model_versions
        )
        previous_function_query_sqls: dict[str, str] = read_previous_function_query_sqls(
            backend=backend,
            state_connection=state_connection,
            schema=config.schema,
            graph=graph,
        )
        model_targets: dict[str, CompiledRelationTarget] = {
            model.name: model.target for model in graph.project.models
        }
        physical_relations: dict[str, PhysicalRelationRecord] = {}
        for model_name, version_hash in bound_version_hashes.items():
            relation: PhysicalRelationRecord | None = backend.get_physical_relation(
                state_connection,
                schema=config.schema,
                model_name=model_name,
                version_hash=version_hash,
            )
            if relation is not None:
                physical_relations[model_name] = relation
        deferred_targets: dict[str, CompiledRelationTarget] = {
            model_name: build_target_from_physical_relation(
                adapter=adapter,
                relation=relation,
                fallback_target=model_targets[model_name],
            )
            for model_name, relation in physical_relations.items()
            if model_name in model_targets
        }
        deferred_relations: dict[str, RelationInfo] = {
            model_name: RelationInfo(
                database=relation.database_name,
                schema=relation.schema_name,
                name=relation.relation_name,
                relation_type=relation.relation_type,
            )
            for model_name, relation in physical_relations.items()
        }
        return (
            bound_version_hashes,
            build_bound_local_hashes(model_versions),
            deferred_targets,
            deferred_relations,
            previous_query_sqls,
            previous_metadata_jsons,
            previous_function_query_sqls,
        )
    finally:
        backend.close(state_connection)


def _resolve_virtual_environment_name(
    *,
    physical_environment_name: str | None,
    virtual_environment_name: str | None,
) -> str | None:
    return virtual_environment_name or physical_environment_name
