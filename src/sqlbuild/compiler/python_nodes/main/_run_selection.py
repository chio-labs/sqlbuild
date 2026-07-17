"""Run-command Python-node selection entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes._helpers.inventory import build_python_node_graph
from sqlbuild.compiler.python_nodes._helpers.run_selectors import resolve_python_sql_run_selectors
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunSelection,
)


def resolve_python_sql_run_selection_from_inputs(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    project_graph: ProjectGraph,
    discovered_inputs: DiscoveredProjectInputs,
) -> PythonSqlRunSelection:
    """Resolve run selectors using discovered Python-node project inputs."""

    python_graph: PythonNodeGraph = build_python_node_graph(discovered_inputs=discovered_inputs)
    return resolve_python_sql_run_selectors(
        select=select,
        exclude=exclude,
        project_graph=project_graph,
        python_graph=python_graph,
    )
