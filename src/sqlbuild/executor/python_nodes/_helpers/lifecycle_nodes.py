"""Build generic lifecycle scheduler nodes for Python DAG execution regions."""

from __future__ import annotations

from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonNode,
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
)
from sqlbuild.executor.scheduling.models import LifecycleExecutionNode


def build_ingress_lifecycle_nodes(
    *, plan: PythonSqlRunLifecyclePlan, python_graph: PythonNodeGraph
) -> tuple[LifecycleExecutionNode, ...]:
    """Build schedulable pre-SQL Python/loader nodes from a lifecycle plan."""

    return _build_python_lifecycle_nodes(
        selected_names=plan.ingress_python_node_names,
        python_graph=python_graph,
    )


def build_read_side_python_lifecycle_nodes(
    *, plan: PythonSqlRunLifecyclePlan, python_graph: PythonNodeGraph
) -> tuple[LifecycleExecutionNode, ...]:
    """Build schedulable SQL-read Python nodes from a lifecycle plan."""

    return _build_python_lifecycle_nodes(
        selected_names=plan.read_side_python_node_names,
        python_graph=python_graph,
    )


def _build_python_lifecycle_nodes(
    *, selected_names: frozenset[str], python_graph: PythonNodeGraph
) -> tuple[LifecycleExecutionNode, ...]:
    return tuple(
        _build_python_lifecycle_node(
            node=python_graph.nodes_by_name[node_name],
            selected_names=selected_names,
            python_graph=python_graph,
        )
        for node_name in sorted(selected_names)
    )


def _build_python_lifecycle_node(
    *,
    node: DiscoveredPythonNode,
    selected_names: frozenset[str],
    python_graph: PythonNodeGraph,
) -> LifecycleExecutionNode:
    return LifecycleExecutionNode(
        name=node.name,
        kind=node.kind.value,
        upstream_names=tuple(
            upstream_name
            for upstream_name in python_graph.upstream_deps.get(node.name, ())
            if upstream_name in selected_names
        ),
        payload=node,
    )
