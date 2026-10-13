"""Plan a compiled project over an open warehouse connection."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.materializations import load_custom_materializations
from sqlbuild.compiler.pipeline._helpers.python_plan_entries import (
    build_python_run_plan_outputs,
    python_read_source_names_for,
)
from sqlbuild.compiler.pipeline.models import (
    CompilePipelineOptions,
    CompilePipelineResult,
    PythonRunPlanOutputs,
)
from sqlbuild.compiler.planner.main.execution.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    DeferralInputs,
    PlannerOverrides,
    PlannerPolicies,
    PlannerSelection,
    PlanOutput,
)
from sqlbuild.compiler.python_nodes.main._run_selection import (
    resolve_python_sql_run_selection_from_inputs,
)
from sqlbuild.compiler.python_nodes.models import PythonSqlRunSelection
from sqlbuild.spec.contracts.models import TargetConfig


def build_pipeline_result(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection: Any,
    project: CompiledProjectView,
    options: CompilePipelineOptions,
    on_progress: Callable[[str], None] | None = None,
) -> CompilePipelineResult:
    """Plan the compiled project over an open connection and attach Python node plans."""

    select: tuple[str, ...] = options.select
    exclude: tuple[str, ...] = options.exclude
    deferred_locations: dict[str, CompiledRelationLocation] | None = None
    deferred_relations: dict[str, RelationInfo] | None = None
    if options.defer_to is not None:
        deferred_target_config: TargetConfig = _native.resolve_deferred_target_config(
            discovered_inputs=discovered_inputs,
            defer_to=options.defer_to,
            current_target_name=project.effective_target_name,
        )
        deferred_locations = _native.build_deferred_locations(
            project=project,
            deferred_target_config=deferred_target_config,
            effective_vars=project.effective_vars,
            default_schema=adapter.default_schema(),
            default_database=adapter.default_database(),
            render_qualified_name=adapter.render_qualified_name,
        )
        deferred_relations = _native.gather_deferred_relations(
            adapter=adapter,
            connection=connection,
            deferred_locations=deferred_locations,
        )

    selected_sql_keys: frozenset[CompiledObjectKey] | None = None
    selected_python_node_names: frozenset[str] = frozenset()
    python_read_source_names: frozenset[str] = frozenset()
    run_selection: PythonSqlRunSelection | None = None
    if not options.sql_test_selection.models_selected:
        selected_sql_keys = frozenset()
    elif options.resolve_python_run_selectors:
        run_selection = resolve_python_sql_run_selection_from_inputs(
            select=select,
            exclude=exclude,
            project_graph=_native.build_project_graph_from_compiled_project(project=project),
            discovered_inputs=discovered_inputs,
        )
        selected_sql_keys = run_selection.sql_keys
        selected_python_node_names = run_selection.python_node_names
        python_read_source_names = python_read_source_names_for(
            discovered_inputs=discovered_inputs, python_node_names=selected_python_node_names
        )

    plan_output: PlanOutput = build_execution_plan(
        project=project,
        adapter=adapter,
        connection=connection,
        selection=PlannerSelection(
            select=select,
            exclude=exclude,
            selected_keys=selected_sql_keys,
            python_read_source_names=python_read_source_names,
            sql_test_selection=options.sql_test_selection,
        ),
        overrides=PlannerOverrides(
            cursor_overrides=options.cursor_overrides,
            full_refresh=options.full_refresh,
            reload_sources=options.reload_sources,
            max_microbatches=options.max_microbatches,
        ),
        deferral=DeferralInputs(
            deferred_locations=deferred_locations,
            deferred_relations=deferred_relations,
            defer_sources_to=options.defer_sources_to,
            source_deferral_enabled=options.source_deferral_enabled,
        ),
        policies=PlannerPolicies(
            auto_load_sources=options.auto_load_sources,
            selection_diagnostics=options.selection_diagnostics,
            plan_sql_tests=options.plan_sql_tests,
            record_migration_fingerprints=options.record_migration_fingerprints,
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
    )

    return CompilePipelineResult(
        project=project,
        plan_output=python_outputs.plan_output,
        custom_materializations=custom_materializations,
        python_node_names=python_outputs.selected_python_node_names,
        python_plan_entries=python_outputs.python_plan_entries,
    )
