"""Build display-ready Python entries for plan output."""

from __future__ import annotations

from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import PlanOutput, PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonNode,
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import PythonNodeKind, PythonRunPhase


def build_python_plan_entries(
    *, lifecycle_plan: PythonSqlRunLifecyclePlan, python_graph: PythonNodeGraph
) -> tuple[PythonPlanEntry, ...]:
    """Return task/asset plan entries ordered by lifecycle dependency readiness."""

    entries: list[PythonPlanEntry] = []
    node_name: str
    for node_name in _ordered_python_names(
        selected_names=lifecycle_plan.ingress_python_node_names,
        python_graph=python_graph,
    ):
        node: DiscoveredPythonNode = python_graph.nodes_by_name[node_name]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            entries.append(
                PythonPlanEntry(
                    name=node.name,
                    kind=node.kind,
                    phase=PythonRunPhase.PRE_SQL_INGRESS,
                    provider_usages=node.provider_usages,
                )
            )
    for node_name in _ordered_python_names(
        selected_names=lifecycle_plan.read_side_python_node_names,
        python_graph=python_graph,
    ):
        node = python_graph.nodes_by_name[node_name]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            entries.append(
                PythonPlanEntry(
                    name=node.name,
                    kind=node.kind,
                    phase=PythonRunPhase.READ_SIDE,
                    provider_usages=node.provider_usages,
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


def python_upstream_closure(*, node_name: str, python_graph: PythonNodeGraph) -> frozenset[str]:
    """Return all upstream Python node names for one Python node."""

    names: set[str] = set()
    pending: list[str] = list(python_graph.upstream_deps.get(node_name, ()))
    while pending:
        current: str = pending.pop(0)
        if current in names:
            continue
        names.add(current)
        pending.extend(python_graph.upstream_deps.get(current, ()))
    return frozenset(names)


def build_skipped_task_asset_ingress_warnings(
    *,
    plan_output: PlanOutput,
    run_selection: PythonSqlRunSelection,
    python_graph: PythonNodeGraph,
) -> tuple[PlanWarning, ...]:
    """Return warnings for skipped task/asset deps of planned source loaders."""

    warnings: list[PlanWarning] = []
    entry_loader_names: frozenset[str] = frozenset(
        entry.loader for entry in plan_output.source_load_entries
    )
    loader_name: str
    for loader_name in sorted(entry_loader_names):
        if loader_name not in python_graph.nodes_by_name:
            continue
        upstream_name: str
        for upstream_name in sorted(
            python_upstream_closure(node_name=loader_name, python_graph=python_graph)
        ):
            if upstream_name in run_selection.python_node_names:
                continue
            upstream_node: DiscoveredPythonNode = python_graph.nodes_by_name[upstream_name]
            if upstream_node.kind not in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
                continue
            warnings.append(
                PlanWarning(
                    model_name=None,
                    severity=WarningSeverity.WARNING,
                    message=(
                        f"Source loader '{loader_name}' has unselected upstream "
                        f"{upstream_node.kind.value} '{upstream_name}'. SQLBuild will not run "
                        "it and cannot verify side effects or payload availability; use "
                        f"+source:{loader_name} to refresh upstream ingress dependencies."
                    ),
                    code="P501",
                )
            )
    return tuple(warnings)
