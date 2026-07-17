"""Virtual-mode planning entrypoint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.pipeline.main.graph import build_project_graph
from sqlbuild.compiler.pipeline.models import CompilePipelineResult, ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.planner.types import WorkSelectionPolicy
from sqlbuild.compiler.python_nodes.models import PythonSqlRunSelection
from sqlbuild.runtime.contracts.main.open_connection import open_connection_with_hooks
from sqlbuild.runtime.contracts.models import ConnectionHooks
from sqlbuild.virtual.planner._helpers.bound_state import (
    read_virtual_bound_state,
    resolve_virtual_environment_name,
)
from sqlbuild.virtual.planner._helpers.output import (
    attach_virtual_plan_metadata,
    build_virtual_plan_output,
    rewrite_virtual_plan_entries,
)
from sqlbuild.virtual.planner._helpers.planning import resolve_virtual_model_selection
from sqlbuild.virtual.planner.main._python_identities import read_bound_virtual_python_identities
from sqlbuild.virtual.planner.main._python_plan_entries import build_virtual_python_plan_entries
from sqlbuild.virtual.planner.main._python_run_selection import build_virtual_python_run_selection
from sqlbuild.virtual.planner.main._semantics import build_virtual_plan_semantics
from sqlbuild.virtual.planner.models import (
    VirtualBoundState,
    VirtualPlanOptions,
    VirtualPlanSemantics,
)


def run_virtual_plan_pipeline(
    *,
    project_dir: Path,
    discovered_inputs: DiscoveredProjectInputs,
    adapter: BaseAdapter,
    connection_config: dict[str, object] | None = None,
    options: VirtualPlanOptions | None = None,
    hooks: ConnectionHooks | None = None,
) -> CompilePipelineResult:
    """Run the planner-only virtual pipeline for `sqb plan`."""

    if connection_config is None:
        raise PlannerInputError("virtual planning requires explicit connection_config")
    resolved: VirtualPlanOptions = options if options is not None else VirtualPlanOptions()
    resolved_hooks: ConnectionHooks = hooks if hooks is not None else ConnectionHooks()
    graph: ProjectGraph = build_project_graph(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        selected_target=resolved.selected_target,
        no_sql_validation=resolved.no_sql_validation,
        cli_vars=resolved.cli_vars,
        external_sql_reference_resolver=resolved.external_sql_reference_resolver,
    )
    connection: Any = open_connection_with_hooks(
        adapter=adapter,
        connection_config=connection_config,
        hooks=resolved_hooks,
    )
    try:
        bound: VirtualBoundState = read_virtual_bound_state(
            discovered_inputs=discovered_inputs,
            project_dir=project_dir,
            adapter=adapter,
            warehouse_connection=connection,
            graph=graph,
            selected_target=resolved.selected_target,
            virtual_environment_name=resolved.virtual_environment_name,
        )
        semantics: VirtualPlanSemantics = build_virtual_plan_semantics(
            graph=graph,
            bound_refs=bound.refs,
            bound_model_versions=bound.model_versions,
            bound_seed_refs=bound.seed_refs,
            source_freshness_records=bound.source_freshness_records,
        )
        default_model_selection: tuple[str, ...] = (
            semantics.default_selection
            if resolved.changes_only
            else tuple(sorted(model.name for model in graph.project.models))
        )
        effective_select: tuple[str, ...] = resolve_virtual_model_selection(
            graph=graph,
            select=resolved.select,
            exclude=resolved.exclude,
            default_selection=default_model_selection,
            stale_model_names=semantics.stale_model_names,
            include_stale_upstreams=resolved.include_stale_upstreams,
            work_selection_policy=(
                WorkSelectionPolicy.STALE_ONLY
                if resolved.changes_only
                else WorkSelectionPolicy.ALL_SELECTED
            ),
        )
        selected_seed_names: tuple[str, ...] = (
            (
                semantics.stale_seed_names
                if resolved.changes_only
                else tuple(sorted(seed.name for seed in graph.project.seeds))
            )
            if not resolved.select and not resolved.exclude
            else ()
        )
        plan_output: PlanOutput = build_virtual_plan_output(
            graph=graph,
            adapter=adapter,
            connection=connection,
            effective_select_with_seeds=tuple(
                sorted(set(effective_select) | set(selected_seed_names))
            ),
            options=resolved,
            bound=bound,
            discovered_inputs=discovered_inputs,
            on_progress=resolved_hooks.on_progress,
        )
        plan_output = rewrite_virtual_plan_entries(
            plan_output=plan_output,
            stale_root_reasons=semantics.stale_root_reasons,
            stale_root_causes=semantics.stale_root_causes,
            stale_root_cause_reasons=semantics.stale_root_cause_reasons,
            previous_query_sqls=semantics.bound_previous_query_sqls,
            current_metadata_jsons=semantics.expected_metadata_jsons,
            previous_metadata_jsons=semantics.bound_metadata_jsons,
            previous_function_query_sqls=bound.previous_function_query_sqls,
            run_despite_unchanged=semantics.run_despite_unchanged,
            seed_plan_reasons=semantics.seed_plan_reasons,
        )
        plan_output = attach_virtual_plan_metadata(
            plan_output=plan_output,
            graph=graph,
            semantics=semantics,
            bound=bound,
            target_name=resolve_virtual_environment_name(
                physical_target_name=graph.project.effective_target_name,
                virtual_environment_name=resolved.virtual_environment_name,
            ),
            effective_select=effective_select,
        )
        python_selection: PythonSqlRunSelection = build_virtual_python_run_selection(
            discovered_inputs=discovered_inputs,
            graph=graph,
            plan_output=plan_output,
            select=resolved.select,
            exclude=resolved.exclude,
            selected_model_names=effective_select,
            include_python=resolved.include_python,
        )
        previous_python_identities: dict[tuple[str, str], Fingerprint] = (
            read_bound_virtual_python_identities(
                discovered_inputs=discovered_inputs,
                project_dir=project_dir,
                virtual_environment_name=resolved.virtual_environment_name,
            )
        )
        return CompilePipelineResult(
            project=graph.project,
            plan_output=plan_output,
            python_node_names=python_selection.python_node_names,
            python_plan_entries=build_virtual_python_plan_entries(
                discovered_inputs=discovered_inputs,
                selection=python_selection,
                previous_identities=previous_python_identities,
            ),
        )
    finally:
        adapter.close(connection)
