"""Virtual Python-node closure helpers."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.models import DiscoveredPythonNode, PythonNodeGraph
from sqlbuild.compiler.python_nodes.types import PythonNodeKind


def planned_source_loader_python_names(
    *, plan_output: PlanOutput, python_graph: PythonNodeGraph
) -> frozenset[str]:
    """Return source-loader Python names required by the current virtual plan."""

    loader_names: frozenset[str] = frozenset(
        entry.loader
        for entry in plan_output.source_load_entries
        if entry.loader in python_graph.nodes_by_name
        and python_graph.nodes_by_name[entry.loader].kind == PythonNodeKind.LOADER
    )
    return loader_names | python_upstream_closure(
        selected_python_names=loader_names,
        python_graph=python_graph,
    )


def sql_attached_python_names(
    *, selected_sql_names: frozenset[str], python_graph: PythonNodeGraph
) -> frozenset[str]:
    """Return read-side Python names attached to selected SQL resources."""

    mutable_direct_names: set[str] = set()
    for node in python_graph.nodes:
        if node.kind not in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            continue
        if any(sql_dep.name in selected_sql_names for sql_dep in node.sql_deps):
            mutable_direct_names.add(node.name)
    direct_names: frozenset[str] = frozenset(mutable_direct_names)
    downstream_names: frozenset[str] = python_downstream_closure(
        selected_python_names=direct_names,
        python_graph=python_graph,
    )
    return direct_names | downstream_names


def python_upstream_closure(
    *, selected_python_names: frozenset[str], python_graph: PythonNodeGraph
) -> frozenset[str]:
    """Return all Python upstreams for selected Python nodes."""

    names: set[str] = set()
    pending: list[str] = []
    for node_name in selected_python_names:
        pending.extend(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)


def python_downstream_closure(
    *, selected_python_names: frozenset[str], python_graph: PythonNodeGraph
) -> frozenset[str]:
    """Return task/asset downstreams for selected Python nodes."""

    names: set[str] = set()
    pending: list[str] = []
    for node_name in selected_python_names:
        pending.extend(python_graph.downstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        node: DiscoveredPythonNode = python_graph.nodes_by_name[current]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            names.add(current)
            pending.extend(python_graph.downstream_deps.get(current, ()))
    return frozenset(names)
