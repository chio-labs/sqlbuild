"""Build display-ready Python entries for plan output."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonNode,
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonRunRegion


def build_python_plan_entries(
    *, lifecycle_plan: PythonSqlRunLifecyclePlan, python_graph: PythonNodeGraph
) -> tuple[PythonPlanEntry, ...]:
    """Return task/asset plan entries ordered by lifecycle dependency readiness."""

    entries: list[PythonPlanEntry] = []
    node_name: str
    for node_name in _ordered_python_names(
        selected_names=lifecycle_plan.region_1_python_node_names,
        python_graph=python_graph,
    ):
        node: DiscoveredPythonNode = python_graph.nodes_by_name[node_name]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            entries.append(
                PythonPlanEntry(
                    name=node.name,
                    kind=node.kind,
                    region=PythonRunRegion.PRE_SQL_INGRESS,
                )
            )
    for node_name in _ordered_python_names(
        selected_names=lifecycle_plan.region_2_python_node_names,
        python_graph=python_graph,
    ):
        node = python_graph.nodes_by_name[node_name]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            entries.append(
                PythonPlanEntry(
                    name=node.name,
                    kind=node.kind,
                    region=PythonRunRegion.SQL_READ_PYTHON,
                )
            )
    return tuple(entries)


def _ordered_python_names(
    *, selected_names: frozenset[str], python_graph: PythonNodeGraph
) -> tuple[str, ...]:
    upstream_names: dict[str, tuple[str, ...]] = {
        name: tuple(
            upstream_name
            for upstream_name in python_graph.upstream_deps.get(name, ())
            if upstream_name in selected_names
        )
        for name in selected_names
    }
    downstream_names: dict[str, list[str]] = {name: [] for name in selected_names}
    node_name: str
    upstream_name: str
    for node_name, upstreams in upstream_names.items():
        for upstream_name in upstreams:
            downstream_names[upstream_name].append(node_name)
    in_degree: dict[str, int] = {name: len(upstreams) for name, upstreams in upstream_names.items()}
    ready: list[str] = sorted(name for name, degree in in_degree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        node_name = ready.pop(0)
        ordered.append(node_name)
        for downstream_name in sorted(downstream_names[node_name]):
            in_degree[downstream_name] -= 1
            if in_degree[downstream_name] == 0:
                ready.append(downstream_name)
                ready.sort()
    return tuple(ordered)
