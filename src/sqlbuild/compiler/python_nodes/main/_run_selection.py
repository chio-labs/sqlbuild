"""Run-command Python-node selection entrypoint."""

from __future__ import annotations

from sqlbuild._native import compiled_graph_keys, resolve_python_sql_run_selection
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes._helpers.user_inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes.models import PythonSqlRunSelection


def resolve_python_sql_run_selection_from_inputs(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    project_graph: ProjectGraph,
    discovered_inputs: DiscoveredProjectInputs,
) -> PythonSqlRunSelection:
    """Resolve run selectors using discovered Python-node project inputs."""

    sql_keys, python_node_names = resolve_python_sql_run_selection(
        project_graph=project_graph,
        python_graph=build_python_node_graph(discovered_inputs=discovered_inputs),
        select=select,
        exclude=exclude,
    )
    return PythonSqlRunSelection(
        sql_keys=compiled_graph_keys(sql_keys), python_node_names=frozenset(python_node_names)
    )
