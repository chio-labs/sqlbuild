"""Run-command selector helpers for SQL resources and executable Python nodes."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.python_nodes.helpers.unified_selectors import resolve_python_sql_selectors
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
    """Resolve `sqb run` selectors across SQL resources and Python nodes.

    Python checks are intentionally excluded from `run`; use `sqb check` once check execution
    is wired.
    """

    selection: PythonSqlSelection = resolve_python_sql_selectors(
        select=select,
        exclude=exclude,
        project_graph=project_graph,
        python_graph=python_graph,
    )
    selected_check_names: frozenset[str] = frozenset(
        name
        for name in selection.python_node_names
        if python_graph.nodes_by_name[name].kind == PythonNodeKind.CHECK
    )
    if select and selected_check_names:
        check_list: str = ", ".join(sorted(selected_check_names))
        raise PlannerInputError(
            f"sqb run does not execute Python checks: {check_list}. Use sqb check instead."
        )
    runnable_python_names: frozenset[str] = frozenset(
        name
        for name in selection.python_node_names
        if python_graph.nodes_by_name[name].kind != PythonNodeKind.CHECK
    )
    expanded_python_names: frozenset[str] = runnable_python_names | frozenset(
        upstream_name
        for name in runnable_python_names
        for upstream_name in _python_upstream_closure(node_name=name, python_graph=python_graph)
        if python_graph.nodes_by_name[upstream_name].kind != PythonNodeKind.CHECK
    )
    return PythonSqlRunSelection(
        sql_keys=selection.sql_keys
        | frozenset(
            CompiledObjectKey(resource_type=CompiledResourceType.SOURCE, name=name)
            for name in expanded_python_names
            if python_graph.nodes_by_name[name].kind == PythonNodeKind.LOADER
            and name not in _terminal_loader_names(project_graph=project_graph)
        ),
        python_node_names=expanded_python_names,
    )


def _terminal_loader_names(*, project_graph: ProjectGraph) -> frozenset[str]:
    return frozenset(
        source.source_entry.loader
        for source in project_graph.project.sources
        if source.source_entry.loader is not None
    )


def _python_upstream_closure(*, node_name: str, python_graph: PythonNodeGraph) -> frozenset[str]:
    names: set[str] = set()
    pending: list[str] = list(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)
