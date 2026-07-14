"""Virtual-mode Python node run-selection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_selection_graph import (
    resolve_python_sql_run_selection_from_graph,
)
from sqlbuild.compiler.python_nodes.main.selection_validation import validate_python_sql_selection
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunSelection,
    PythonSqlSelection,
)
from sqlbuild.virtual.planner._helpers.python_node_closure import (
    planned_source_loader_python_names,
    python_upstream_closure,
    sql_attached_python_names,
)


def build_virtual_python_run_selection(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    graph: ProjectGraph,
    plan_output: PlanOutput,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    selected_model_names: tuple[str, ...],
    include_python: bool,
) -> PythonSqlRunSelection:
    """Return selected virtual Python nodes plus SQL keys used for lifecycle planning."""

    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=discovered_inputs
    )
    selected_python_names: frozenset[str] = planned_source_loader_python_names(
        plan_output=plan_output, python_graph=python_graph
    )
    validation_sql_keys: frozenset[CompiledObjectKey] = frozenset(plan_output.selected_keys)
    if include_python:
        raw_select: tuple[str, ...] = select or selected_model_names
        if raw_select:
            run_selection: PythonSqlRunSelection = resolve_python_sql_run_selection_from_graph(
                select=raw_select,
                exclude=exclude,
                project_graph=graph,
                python_graph=python_graph,
            )
            selected_python_names = selected_python_names | run_selection.python_node_names
            validation_sql_keys = validation_sql_keys | run_selection.sql_keys
        selected_python_names = selected_python_names | sql_attached_python_names(
            selected_sql_names=frozenset(key.name for key in plan_output.selected_keys),
            python_graph=python_graph,
        )
    selected_python_names = selected_python_names | python_upstream_closure(
        selected_python_names=selected_python_names,
        python_graph=python_graph,
    )
    validate_python_sql_selection(
        selection=PythonSqlSelection(
            sql_keys=validation_sql_keys,
            python_node_names=selected_python_names,
        ),
        project_graph=graph,
        python_graph=python_graph,
    )
    return PythonSqlRunSelection(
        sql_keys=frozenset(plan_output.selected_keys),
        python_node_names=selected_python_names,
    )
