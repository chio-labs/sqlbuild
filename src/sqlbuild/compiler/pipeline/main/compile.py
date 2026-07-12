"""Full compile-and-plan pipeline producing CLI artifacts."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.models import RelationInfo
from sqlbuild.compiler.compile.main.effective_config import build_effective_connection_config
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.helpers.lineage_graph import (
    build_lineage_downstream_deps,
    build_lineage_upstream_deps,
)
from sqlbuild.compiler.helpers.selector_indexes import (
    build_model_path_index,
    build_model_tag_index,
)
from sqlbuild.compiler.pipeline.helpers.deferred_locations import (
    build_deferred_locations,
    gather_deferred_relations,
    resolve_deferred_target_config,
)
from sqlbuild.compiler.pipeline.helpers.graph import build_static_all_keys
from sqlbuild.compiler.pipeline.helpers.materializations import load_custom_materializations
from sqlbuild.compiler.pipeline.helpers.python_plan_entries import build_python_run_plan_outputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from sqlbuild.compiler.pipeline.main.prepare_versions import (
    load_custom_prepare_version_functions,
)
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
    ProjectGraph,
    PythonRunPlanOutputs,
)
from sqlbuild.compiler.planner.main.planning.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import StandardScopePruning, WorkSelectionPolicy
from sqlbuild.compiler.python_nodes.main.run_selection import (
    resolve_python_sql_run_selection_from_inputs,
)
from sqlbuild.compiler.python_nodes.models import PythonSqlRunSelection
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.spec.models.project import TargetConfig


def run_compile_pipeline(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    options: CompilePipelineOptions | None = None,
    hooks: ConnectionHooks | None = None,
) -> CompilePipelineResult:
    """Run compile inputs, assembly, planning, and manifest generation."""

    resolved_options: CompilePipelineOptions = (
        options if options is not None else CompilePipelineOptions()
    )
    resolved_hooks: ConnectionHooks = hooks if hooks is not None else ConnectionHooks()
    on_progress: Callable[[str], None] | None = resolved_hooks.on_progress
    effective_config: dict[str, object] = (
        resolved_options.connection_config
        if resolved_options.connection_config is not None
        else build_effective_connection_config(
            discovered_inputs=discovered_inputs,
            selected_target=resolved_options.selected_target,
            cli_vars=resolved_options.cli_vars,
        )
    )
    if on_progress is not None:
        on_progress("Compiling project...")
    compile_start: float = time.monotonic()
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=resolved_options.selected_target,
        no_sql_validation=resolved_options.no_sql_validation,
        cli_vars=resolved_options.cli_vars,
        external_sql_reference_resolver=resolved_options.external_sql_reference_resolver,
        resolved_connection=effective_config,
    )
    if on_progress is not None:
        on_progress(f"Compiled project. ({time.monotonic() - compile_start:.2f}s)")
    if resolved_hooks.on_connection_start is not None:
        resolved_hooks.on_connection_start(1)
    start: float = time.monotonic()
    try:
        connection: Any = adapter.connect(effective_config)
    except Exception:
        if resolved_hooks.on_connection_error is not None:
            resolved_hooks.on_connection_error(1, elapsed_seconds=time.monotonic() - start)
        raise
    if resolved_hooks.on_connection_complete is not None:
        resolved_hooks.on_connection_complete(1, elapsed_seconds=time.monotonic() - start)
    try:
        return _build_result(
            discovered_inputs=discovered_inputs,
            adapter=adapter,
            connection=connection,
            project=project,
            options=resolved_options,
            on_progress=on_progress,
        )
    finally:
        adapter.close(connection)


def _build_result(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection: Any,
    project: CompiledProject,
    options: CompilePipelineOptions,
    on_progress: Callable[[str], None] | None = None,
) -> CompilePipelineResult:
    work_selection_policy: WorkSelectionPolicy = (
        WorkSelectionPolicy.STALE_ONLY if options.changes_only else WorkSelectionPolicy.ALL_SELECTED
    )
    select: tuple[str, ...] = options.select
    exclude: tuple[str, ...] = options.exclude
    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    deferred_relations: dict[str, RelationInfo] | None = None
    if options.defer_to is not None:
        deferred_target_config: TargetConfig = resolve_deferred_target_config(
            discovered_inputs=discovered_inputs,
            defer_to=options.defer_to,
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
    if options.resolve_python_run_selectors:
        run_selection = resolve_python_sql_run_selection_from_inputs(
            select=select,
            exclude=exclude,
            project_graph=_build_project_graph(project=project),
            discovered_inputs=discovered_inputs,
        )
        selected_sql_keys = run_selection.sql_keys
        selected_python_node_names = run_selection.python_node_names

    custom_prepare_version_functions: dict[str, Any] = load_custom_prepare_version_functions(
        discovered_inputs.materialization_files
    )

    plan_output: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
        selection=PlannerSelection(
            select=select,
            exclude=exclude,
            selected_keys=selected_sql_keys,
        ),
        overrides=PlannerOverrides(
            cursor_overrides=options.cursor_overrides,
            full_refresh=options.full_refresh,
            reload_sources=options.reload_sources,
        ),
        deferral=DeferralInputs(
            deferred_locations=deferred_locations,
            deferred_relations=deferred_relations,
            defer_sources_to=options.defer_sources_to,
            source_deferral_enabled=options.source_deferral_enabled,
        ),
        policies=PlannerPolicies(
            standard_scope_pruning=(
                StandardScopePruning.PRUNE_UNCHANGED
                if work_selection_policy == WorkSelectionPolicy.STALE_ONLY
                else StandardScopePruning.NONE
            ),
            auto_load_sources=options.auto_load_sources,
            custom_prepare_version_materializations=frozenset(
                custom_prepare_version_functions.keys()
            ),
        ),
        on_progress=on_progress,
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    custom_materializations: dict[str, Any] = load_custom_materializations(
        discovered_inputs.materialization_files
    )
    python_outputs: PythonRunPlanOutputs = build_python_run_plan_outputs(
        discovered_inputs=discovered_inputs,
        plan_output=plan_output,
        run_selection=run_selection,
        selected_python_node_names=selected_python_node_names,
        work_selection_policy=work_selection_policy,
    )

    return CompilePipelineResult(
        project=project,
        plan_output=python_outputs.plan_output,
        custom_materializations=custom_materializations,
        custom_prepare_version_functions=custom_prepare_version_functions,
        python_node_names=python_outputs.selected_python_node_names,
        python_plan_entries=python_outputs.python_plan_entries,
    )


def _build_project_graph(*, project: CompiledProject) -> ProjectGraph:
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_upstream_deps(project)
    )
    return ProjectGraph(
        project=project,
        upstream_deps=upstream_deps,
        downstream_deps=build_lineage_downstream_deps(upstream_deps),
        tag_index=build_model_tag_index(project),
        path_index=build_model_path_index(project),
        all_keys=build_static_all_keys(project),
    )
