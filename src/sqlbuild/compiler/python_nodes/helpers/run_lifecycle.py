"""Lifecycle classification for `sqb run` SQL/Python selections."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes.models import (
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind


def build_python_sql_run_lifecycle_plan(
    *, selection: PythonSqlRunSelection, python_graph: PythonNodeGraph
) -> PythonSqlRunLifecyclePlan:
    """Classify selected run nodes into lifecycle-aware execution regions."""

    selected_python_names: frozenset[str] = selection.python_node_names
    selected_loader_names: frozenset[str] = frozenset(
        name
        for name in selected_python_names
        if python_graph.nodes_by_name[name].kind == PythonNodeKind.LOADER
    )
    region_1_names: frozenset[str] = selected_loader_names | frozenset(
        upstream_name
        for loader_name in selected_loader_names
        for upstream_name in _upstream_closure(node_name=loader_name, python_graph=python_graph)
        if upstream_name in selected_python_names
        if python_graph.nodes_by_name[upstream_name].kind
        in {PythonNodeKind.TASK, PythonNodeKind.ASSET, PythonNodeKind.LOADER}
    )
    region_2_names: frozenset[str] = frozenset(
        name
        for name in selected_python_names - region_1_names
        if python_graph.nodes_by_name[name].kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}
    )
    return PythonSqlRunLifecyclePlan(
        region_1_python_node_names=region_1_names,
        region_1_loader_names=selected_loader_names,
        region_2_sql_keys=selection.sql_keys,
        region_2_python_node_names=region_2_names,
    )


def _upstream_closure(*, node_name: str, python_graph: PythonNodeGraph) -> frozenset[str]:
    names: set[str] = set()
    pending: list[str] = list(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)
