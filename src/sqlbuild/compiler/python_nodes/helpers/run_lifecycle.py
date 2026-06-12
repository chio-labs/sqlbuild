"""Lifecycle classification for build-style SQL/Python selections."""

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
    ingress_names: frozenset[str] = selected_loader_names | frozenset(
        upstream_name
        for loader_name in selected_loader_names
        for upstream_name in _upstream_closure(node_name=loader_name, python_graph=python_graph)
        if upstream_name in selected_python_names
        if python_graph.nodes_by_name[upstream_name].kind
        in {PythonNodeKind.TASK, PythonNodeKind.ASSET, PythonNodeKind.LOADER}
    )
    read_side_names: frozenset[str] = frozenset(
        name
        for name in selected_python_names - ingress_names
        if python_graph.nodes_by_name[name].kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}
    )
    return PythonSqlRunLifecyclePlan(
        ingress_python_node_names=ingress_names,
        ingress_loader_names=selected_loader_names,
        read_side_sql_keys=selection.sql_keys,
        read_side_python_node_names=read_side_names,
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
