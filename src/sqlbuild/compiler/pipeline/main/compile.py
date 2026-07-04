"""Full compile-and-plan pipeline producing CLI artifacts."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.helpers.deferred_locations import (
    build_deferred_locations,
    gather_deferred_relations,
    resolve_deferred_target_config,
)
from sqlbuild.compiler.pipeline.helpers.graph import (
    build_static_all_keys,
    build_static_downstream_deps,
    build_static_upstream_deps,
)
from sqlbuild.compiler.pipeline.helpers.materializations import load_custom_materializations
from sqlbuild.compiler.pipeline.helpers.python_plan_entries import (
    build_python_plan_entries,
    build_skipped_task_asset_ingress_warnings,
)
from sqlbuild.compiler.pipeline.helpers.python_stale_selection import (
    filter_python_node_names_for_selected_sql,
)
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.main.prepare_versions import (
    load_custom_prepare_version_functions,
)
from sqlbuild.compiler.pipeline.models import CompilePipelineResult, ProjectGraph, PythonPlanEntry
from sqlbuild.compiler.planner.main.planning.execution import build_execution_plan
from sqlbuild.compiler.planner.models import CursorOverrides, PlanOutput
from sqlbuild.compiler.planner.types import StandardScopePruning, WorkSelectionPolicy
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.main.run_selection import (
    resolve_python_sql_run_selection_from_inputs,
)
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.shared.helpers.selector_indexes import (
    build_model_path_index,
    build_model_tag_index,
)
from sqlbuild.shared.types import ExternalSqlReferenceResolver
from sqlbuild.spec.models.project import TargetConfig


def run_compile_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None = None,
    no_sql_validation: bool = False,
    defer_to: str | None = None,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
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
    resolve_python_run_selectors: bool = False,
) -> CompilePipelineResult:
    """Run compile inputs, assembly, planning, and manifest generation."""

    effective_config: dict[str, object] = (
        connection_config
        if connection_config is not None
        else build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_target=selected_target,
            cli_vars=cli_vars,
        )
    )
    if on_connection_start is not None:
        on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(effective_config)
    except Exception:
        if on_connection_error is not None:
            on_connection_error(1, time.monotonic() - start)
        raise
    if on_connection_complete is not None:
        on_connection_complete(1, time.monotonic() - start)
    try:
        work_selection_policy: WorkSelectionPolicy = (
            WorkSelectionPolicy.STALE_ONLY if changes_only else WorkSelectionPolicy.ALL_SELECTED
        )
        return _build_result(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            selected_target=selected_target,
            connection=connection,
            no_sql_validation=no_sql_validation,
            defer_to=defer_to,
            defer_sources_to=defer_sources_to,
            source_deferral_enabled=source_deferral_enabled,
            select=select,
            exclude=exclude,
            cursor_overrides=cursor_overrides,
            full_refresh=full_refresh,
            work_selection_policy=work_selection_policy,
            auto_load_sources=auto_load_sources,
            reload_sources=reload_sources,
            cli_vars=cli_vars,
            on_progress=on_progress,
            external_sql_reference_resolver=external_sql_reference_resolver,
            resolve_python_run_selectors=resolve_python_run_selectors,
        )
    finally:
        adapter.close(connection)


def _build_result(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    selected_target: str | None = None,
    connection: Any,
    no_sql_validation: bool,
    defer_to: str | None = None,
    defer_sources_to: str | None = None,
    source_deferral_enabled: bool = True,
    select: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    cursor_overrides: CursorOverrides | None = None,
    full_refresh: bool = False,
    work_selection_policy: WorkSelectionPolicy = WorkSelectionPolicy.ALL_SELECTED,
    auto_load_sources: bool = False,
    reload_sources: bool = False,
    cli_vars: dict[str, object] | None = None,
    on_progress: Callable[[str], None] | None = None,
    external_sql_reference_resolver: ExternalSqlReferenceResolver | None = None,
    resolve_python_run_selectors: bool = False,
) -> CompilePipelineResult:
    if on_progress is not None:
        on_progress("Compiling project...")
    compile_start: float = time.monotonic()
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=selected_target,
        no_sql_validation=no_sql_validation,
        cli_vars=cli_vars,
        external_sql_reference_resolver=external_sql_reference_resolver,
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.monotonic() - compile_start:.2f}s)")

    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    deferred_relations: dict[str, RelationInfo] | None = None
    if defer_to is not None:
        deferred_target_config: TargetConfig = resolve_deferred_target_config(
            discovered_inputs=discovered_inputs,
            defer_to=defer_to,
            current_target_name=project.effective_target_name,
        )
        deferred_locations = build_deferred_locations(
            project=project,
            deferred_target_config=deferred_target_config,
            effective_vars=project.effective_vars,
            default_schema=adapter.default_schema(),
            default_database=adapter.default_database(),
            render_qualified_name=adapter.render_qualified_name,
        )
        deferred_relations = gather_deferred_relations(
            adapter=adapter,
            connection=connection,
            deferred_locations=deferred_locations,
        )

    selected_sql_keys: frozenset[CompiledObjectKey] | None = None
    selected_python_node_names: frozenset[str] = frozenset()
    run_selection: PythonSqlRunSelection | None = None
    if resolve_python_run_selectors:
        run_selection = resolve_python_sql_run_selection_from_inputs(
            select=select,
            exclude=exclude,
            project_graph=_build_project_graph(project=project),
            discovered_inputs=discovered_inputs,
        )
        selected_sql_keys = run_selection.sql_keys if run_selection.python_node_names else None
        selected_python_node_names = run_selection.python_node_names

    custom_prepare_version_functions: dict[str, Any] = load_custom_prepare_version_functions(
        discovered_inputs.materialization_files
    )

    plan_output: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
        select=select,
        exclude=exclude,
        selected_keys=selected_sql_keys,
        deferred_locations=deferred_locations,
        deferred_relations=deferred_relations,
        cursor_overrides=cursor_overrides,
        full_refresh=full_refresh,
        standard_scope_pruning=(
            StandardScopePruning.PRUNE_UNCHANGED
            if work_selection_policy == WorkSelectionPolicy.STALE_ONLY
            else StandardScopePruning.NONE
        ),
        auto_load_sources=auto_load_sources,
        reload_sources=reload_sources,
        on_progress=on_progress,
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
        defer_sources_to=defer_sources_to,
        source_deferral_enabled=source_deferral_enabled,
        custom_prepare_version_materializations=frozenset(custom_prepare_version_functions.keys()),
    )
    custom_materializations: dict[str, Any] = load_custom_materializations(
        discovered_inputs.materialization_files
    )
    python_plan_entries: tuple[PythonPlanEntry, ...] = ()
    if run_selection is not None:
        python_graph: PythonNodeGraph = build_discovered_python_node_graph(
            discovered_inputs=discovered_inputs
        )
        if work_selection_policy == WorkSelectionPolicy.STALE_ONLY:
            selected_python_node_names = filter_python_node_names_for_selected_sql(
                python_graph=python_graph,
                python_node_names=selected_python_node_names,
                selected_sql_keys=plan_output.selected_keys,
            )
        plan_output = replace(
            plan_output,
            warnings=(
                *plan_output.warnings,
                *build_skipped_task_asset_ingress_warnings(
                    plan_output=plan_output,
                    run_selection=run_selection,
                    python_graph=python_graph,
                ),
            ),
        )
        lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
            selection=PythonSqlRunSelection(
                sql_keys=plan_output.selected_keys,
                python_node_names=selected_python_node_names,
            ),
            python_graph=python_graph,
        )
        python_plan_entries = build_python_plan_entries(
            lifecycle_plan=lifecycle_plan,
            python_graph=python_graph,
            previous_identities=plan_output.python_identity_fingerprints,
        )

    return CompilePipelineResult(
        project=project,
        plan_output=plan_output,
        custom_materializations=custom_materializations,
        custom_prepare_version_functions=custom_prepare_version_functions,
        python_node_names=selected_python_node_names,
        python_plan_entries=python_plan_entries,
    )


def _build_project_graph(*, project: CompiledProject) -> ProjectGraph:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_static_upstream_deps(project)
    )
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=build_static_downstream_deps(upstream_deps),
        tag_index=build_model_tag_index(project),
        path_index=build_model_path_index(project),
        all_keys=build_static_all_keys(project),
    )
