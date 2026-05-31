"""Public entrypoint for SQL/Python selection validation."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.python_nodes.helpers.unified_selectors import (
    validate_python_sql_selection_dependencies,
)
from sqlbuild.compiler.python_nodes.models import PythonNodeGraph, PythonSqlSelection


def validate_python_sql_selection(
    *, selection: PythonSqlSelection, project_graph: ProjectGraph, python_graph: PythonNodeGraph
) -> None:
    """Validate a selected SQL/Python graph boundary."""

    validate_python_sql_selection_dependencies(
        selection=selection,
        project_graph=project_graph,
        python_graph=python_graph,
    )
