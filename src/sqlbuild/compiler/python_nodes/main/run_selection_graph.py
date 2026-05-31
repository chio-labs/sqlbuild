"""Run-command Python-node selection entrypoint for prebuilt graphs."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.helpers.run_selectors import resolve_python_sql_run_selectors
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlRunSelection


def resolve_python_sql_run_selection_from_graph(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> PythonSqlRunSelection:
    """Resolve run selectors with an already-built Python-node graph."""

    return resolve_python_sql_run_selectors(
        select=select,
        exclude=exclude,
        project_graph=project_graph,
        python_graph=python_graph,
    )
