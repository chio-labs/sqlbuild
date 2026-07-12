"""Build display-ready Python entries for plan output."""

from __future__ import annotations

from dataclasses import replace

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.pipeline.helpers.python_stale_selection import (
    filter_python_node_names_for_selected_sql,
)
from sqlbuild.compiler.pipeline.models import PythonPlanEntry, PythonRunPlanOutputs
from sqlbuild.compiler.planner.models import PlanOutput, PlanWarning
from sqlbuild.compiler.planner.types import WarningSeverity, WorkSelectionPolicy
from sqlbuild.compiler.python_nodes.main.graph import build_discovered_python_node_graph
from sqlbuild.compiler.python_nodes.main.run_lifecycle import build_python_sql_run_lifecycle
from sqlbuild.compiler.python_nodes.models import (
    DiscoveredPythonNode,
    PythonNodeGraph,
    PythonSqlRunLifecyclePlan,
    PythonSqlRunSelection,
)
from sqlbuild.compiler.python_nodes.types import (
    PythonIdentityStatus,
    PythonNodeKind,
    PythonRunPhase,
)


def build_python_run_plan_outputs(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    plan_output: PlanOutput,
    run_selection: PythonSqlRunSelection | None,
    selected_python_node_names: frozenset[str],
    work_selection_policy: WorkSelectionPolicy,
) -> PythonRunPlanOutputs:
    """Attach python-aware selection warnings and plan entries to the plan output."""

    if run_selection is None:
        return PythonRunPlanOutputs(
            plan_output=plan_output,
            python_plan_entries=(),
            selected_python_node_names=selected_python_node_names,
        )
    python_graph: PythonNodeGraph = build_discovered_python_node_graph(
        discovered_inputs=discovered_inputs
    )
    if work_selection_policy == WorkSelectionPolicy.STALE_ONLY:
        selected_python_node_names = filter_python_node_names_for_selected_sql(
            python_graph=python_graph,
            python_node_names=selected_python_node_names,
            selected_sql_keys=plan_output.selected_keys,
        )
    plan_output = replace(
        plan_output,
        warnings=(
            *plan_output.warnings,
            *build_skipped_task_asset_ingress_warnings(
                plan_output=plan_output,
                run_selection=run_selection,
                python_graph=python_graph,
            ),
        ),
    )
    lifecycle_plan: PythonSqlRunLifecyclePlan = build_python_sql_run_lifecycle(
        selection=PythonSqlRunSelection(
            sql_keys=plan_output.selected_keys,
            python_node_names=selected_python_node_names,
        ),
        python_graph=python_graph,
    )
    return PythonRunPlanOutputs(
        plan_output=plan_output,
        python_plan_entries=build_python_plan_entries(
            lifecycle_plan=lifecycle_plan,
            python_graph=python_graph,
            previous_identities=plan_output.python_identity_fingerprints,
        ),
        selected_python_node_names=selected_python_node_names,
    )


def build_python_plan_entries(
    *,
    lifecycle_plan: PythonSqlRunLifecyclePlan,
    python_graph: PythonNodeGraph,
    previous_identities: dict[tuple[str, str], Fingerprint] | None = None,
) -> tuple[PythonPlanEntry, ...]:
    """Return task/asset plan entries ordered by lifecycle dependency readiness."""

    entries: list[PythonPlanEntry] = []
    resolved_previous_identities: dict[tuple[str, str], Fingerprint] = (
        {} if previous_identities is None else previous_identities
    )
    node_name: str
    for node_name in _ordered_python_names(
        selected_names=lifecycle_plan.ingress_python_node_names,
        python_graph=python_graph,
    ):
        node: DiscoveredPythonNode = python_graph.nodes_by_name[node_name]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            previous_identity: Fingerprint | None = _previous_identity(
                node=node,
                previous_identities=resolved_previous_identities,
            )
            entries.append(
                PythonPlanEntry(
                    name=node.name,
                    kind=node.kind,
                    phase=PythonRunPhase.PRE_SQL_INGRESS,
                    identity_status=_identity_status(
                        node=node,
                        previous_identities=resolved_previous_identities,
                    ),
                    current_definition_json=(
                        node.identity.definition_json if node.identity is not None else None
                    ),
                    previous_definition_json=(
                        previous_identity.definition if previous_identity is not None else None
                    ),
                    current_metadata_json=(
                        node.identity.metadata_json if node.identity is not None else None
                    ),
                    previous_metadata_json=(
                        previous_identity.metadata_json if previous_identity is not None else None
                    ),
                    provider_usages=node.provider_usages,
                )
            )
    for node_name in _ordered_python_names(
        selected_names=lifecycle_plan.read_side_python_node_names,
        python_graph=python_graph,
    ):
        node = python_graph.nodes_by_name[node_name]
        if node.kind in {PythonNodeKind.TASK, PythonNodeKind.ASSET}:
            previous_identity = _previous_identity(
                node=node,
                previous_identities=resolved_previous_identities,
            )
            entries.append(
                PythonPlanEntry(
                    name=node.name,
                    kind=node.kind,
                    phase=PythonRunPhase.READ_SIDE,
                    identity_status=_identity_status(
                        node=node,
                        previous_identities=resolved_previous_identities,
                    ),
                    current_definition_json=(
                        node.identity.definition_json if node.identity is not None else None
                    ),
                    previous_definition_json=(
                        previous_identity.definition if previous_identity is not None else None
                    ),
                    current_metadata_json=(
                        node.identity.metadata_json if node.identity is not None else None
                    ),
                    previous_metadata_json=(
                        previous_identity.metadata_json if previous_identity is not None else None
                    ),
                    provider_usages=node.provider_usages,
                )
            )
    return tuple(entries)


def _ordered_python_names(
    *, selected_names: frozenset[str], python_graph: PythonNodeGraph
) -> tuple[str, ...]:
    upstream_names: dict[str, tuple[str, ...]] = {}
    for name in selected_names:
        selected_upstreams: list[str] = []
        for upstream_name in python_graph.upstream_deps.get(name, ()):
            if upstream_name in selected_names:
                selected_upstreams.append(upstream_name)
        upstream_names[name] = tuple(selected_upstreams)
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


def _identity_status(
    *,
    node: DiscoveredPythonNode,
    previous_identities: dict[tuple[str, str], Fingerprint],
) -> PythonIdentityStatus:
    if node.identity is None:
        return PythonIdentityStatus.UNKNOWN
    previous: Fingerprint | None = _previous_identity(
        node=node,
        previous_identities=previous_identities,
    )
    if previous is None:
        return PythonIdentityStatus.NEW
    if previous.version_hash == node.identity.version_hash:
        return PythonIdentityStatus.UNCHANGED
    return PythonIdentityStatus.CHANGED


def _previous_identity(
    *,
    node: DiscoveredPythonNode,
    previous_identities: dict[tuple[str, str], Fingerprint],
) -> Fingerprint | None:
    if node.identity is None:
        return None
    return previous_identities.get((node.identity.node_type, node.identity.node_name))


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
