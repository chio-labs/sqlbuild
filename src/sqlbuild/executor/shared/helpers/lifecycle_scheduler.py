"""Generic serial scheduler for lifecycle-aware mixed execution graphs."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.models.lifecycle_scheduler import (
    LifecycleExecutionNode,
    LifecycleNodeResult,
    LifecycleSchedulerResult,
)
from sqlbuild.executor.shared.types import LifecycleNodeStatus


def run_lifecycle_scheduler(
    *,
    nodes: tuple[LifecycleExecutionNode, ...],
    handler: Callable[[LifecycleExecutionNode], LifecycleNodeResult],
) -> LifecycleSchedulerResult:
    """Run lifecycle nodes serially in topological order."""

    node_by_name: dict[str, LifecycleExecutionNode] = {node.name: node for node in nodes}
    if len(node_by_name) != len(nodes):
        raise ExecutorInputError("Lifecycle scheduler node names must be unique")
    upstream_names: dict[str, tuple[str, ...]] = _build_upstream_names(
        nodes=nodes,
        node_by_name=node_by_name,
    )
    downstream_names: dict[str, tuple[str, ...]] = _build_downstream_names(
        node_names=tuple(node.name for node in nodes),
        upstream_names=upstream_names,
    )
    in_degree: dict[str, int] = {
        node_name: len(upstreams) for node_name, upstreams in upstream_names.items()
    }
    ready: list[str] = sorted(name for name, degree in in_degree.items() if degree == 0)
    results_by_name: dict[str, LifecycleNodeResult] = {}
    ordered_results: list[LifecycleNodeResult] = []

    while ready:
        node_name: str = ready.pop(0)
        node: LifecycleExecutionNode = node_by_name[node_name]
        dependency_result: LifecycleNodeResult | None = _blocking_dependency_result(
            upstream_names=upstream_names[node_name],
            results_by_name=results_by_name,
        )
        if dependency_result is not None:
            result: LifecycleNodeResult = LifecycleNodeResult(
                name=node.name,
                kind=node.kind,
                status=LifecycleNodeStatus.SKIPPED,
                skip_reason=f"Upstream node did not succeed: {dependency_result.name}",
            )
        else:
            result = handler(node)
        results_by_name[node.name] = result
        ordered_results.append(result)
        downstream_name: str
        for downstream_name in downstream_names[node.name]:
            in_degree[downstream_name] -= 1
            if in_degree[downstream_name] == 0:
                ready.append(downstream_name)
                ready.sort()

    if len(ordered_results) != len(nodes):
        raise ExecutorInputError("Lifecycle scheduler could not resolve all dependencies")
    return LifecycleSchedulerResult(results=tuple(ordered_results))


def _build_upstream_names(
    *,
    nodes: tuple[LifecycleExecutionNode, ...],
    node_by_name: dict[str, LifecycleExecutionNode],
) -> dict[str, tuple[str, ...]]:
    upstream_names: dict[str, tuple[str, ...]] = {}
    node: LifecycleExecutionNode
    for node in nodes:
        upstream_name: str
        for upstream_name in node.upstream_names:
            if upstream_name not in node_by_name:
                raise ExecutorInputError(
                    f"Lifecycle node '{node.name}' depends on unknown node '{upstream_name}'"
                )
        upstream_names[node.name] = node.upstream_names
    return upstream_names


def _build_downstream_names(
    *, node_names: tuple[str, ...], upstream_names: dict[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    downstream: dict[str, list[str]] = {node_name: [] for node_name in node_names}
    node_name: str
    upstreams: tuple[str, ...]
    for node_name, upstreams in upstream_names.items():
        upstream_name: str
        for upstream_name in upstreams:
            downstream[upstream_name].append(node_name)
    return {node_name: tuple(names) for node_name, names in downstream.items()}


def _blocking_dependency_result(
    *,
    upstream_names: tuple[str, ...],
    results_by_name: dict[str, LifecycleNodeResult],
) -> LifecycleNodeResult | None:
    upstream_name: str
    for upstream_name in upstream_names:
        result: LifecycleNodeResult = results_by_name[upstream_name]
        if result.status != LifecycleNodeStatus.SUCCESS:
            return result
    return None
