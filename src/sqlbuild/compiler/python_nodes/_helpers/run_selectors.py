"""Run-command selector helpers for SQL resources and executable Python nodes."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.python_nodes._helpers.unified_selectors import (
    resolve_python_sql_selectors,
    validate_python_sql_selection_dependencies,
)
from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunSelection,
    PythonSqlSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind


def resolve_python_sql_run_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    project_graph: ProjectGraph,
    python_graph: PythonNodeGraph,
) -> PythonSqlRunSelection:
    """Resolve build-style selectors across SQL resources and Python nodes."""

    selection: PythonSqlSelection = resolve_python_sql_selectors(
        select=select,
        exclude=exclude,
        project_graph=project_graph,
        python_graph=python_graph,
        validate_dependencies=False,
    )
    selected_check_names: frozenset[str] = frozenset(
        name
        for name in selection.python_node_names
        if python_graph.nodes_by_name[name].kind == PythonNodeKind.CHECK
    )
    if select and selected_check_names:
        check_list: str = ", ".join(sorted(selected_check_names))
        raise PlannerInputError(
            f"Python checks are not selectable here: {check_list}. Use sqb check instead."
        )
    runnable_python_names: frozenset[str] = frozenset(
        name
        for name in selection.python_node_names
        if python_graph.nodes_by_name[name].kind != PythonNodeKind.CHECK
    )
    run_selection: PythonSqlRunSelection = PythonSqlRunSelection(
        sql_keys=selection.sql_keys,
        python_node_names=runnable_python_names,
    )
    validate_python_sql_selection_dependencies(
        selection=PythonSqlSelection(
            sql_keys=run_selection.sql_keys,
            python_node_names=run_selection.python_node_names,
        ),
        project_graph=project_graph,
        python_graph=python_graph,
    )
    return PythonSqlRunSelection(
        sql_keys=run_selection.sql_keys
        | frozenset(
            CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)
            for name in run_selection.python_node_names
            if python_graph.nodes_by_name[name].kind == PythonNodeKind.LOADER
            and name not in _terminal_loader_names(project_graph=project_graph)
        ),
        python_node_names=run_selection.python_node_names,
    )


def _terminal_loader_names(*, project_graph: ProjectGraph) -> frozenset[str]:
    return frozenset(
        source.source_entry.loader
        for source in project_graph.project.sources
        if source.source_entry.loader is not None
    )
