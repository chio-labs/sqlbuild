"""Graph traversal helpers for planning over compiled project state."""

from __future__ import annotations

import heapq

from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    SqlTestMode,
)
from sqlbuild.compiler.graph.main._attached_audit_gate_edges import attached_audit_gate_edges
from sqlbuild.compiler.graph.main._build_lineage_upstream_deps import build_lineage_upstream_deps
from sqlbuild.compiler.graph.main._hook_read_edges import hook_read_edges
from sqlbuild.compiler.graph.main.invert_edges import invert_edges
from sqlbuild.compiler.graph.main.path_nodes import path_nodes
from sqlbuild.compiler.graph.main.transitive_closure import transitive_closure
from sqlbuild.compiler.graph.models import AttachedAuditGateEdge, HookReadEdge
from sqlbuild.compiler.planner.exceptions import PlannerInputError


def _key_sort_key(key: CompiledObjectKey) -> tuple[str, str]:
    return (key.resource_type, key.name)


def build_execution_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return execution-order edges from lineage and woven SQL test nodes."""

    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    upstream.update({model.key: list(model.deps) for model in project.models})
    upstream.update({source.key: list(source.deps) for source in project.sources})
    upstream.update({seed.key: list(seed.deps) for seed in project.seeds})
    upstream.update({function.key: list(function.deps) for function in project.functions})

    test: CompiledSqlTest
    for test in project.sql_tests:
        if test.mode == SqlTestMode.TABLE_FN:
            upstream[test.key] = list(_function_scope_deps_for_test(test=test))
            continue
        upstream[test.key] = list(_function_deps_for_test(test=test, upstream=upstream))
        for target_key in test.scope_deps:
            if target_key in upstream:
                upstream[target_key].append(test.key)

    edge: AttachedAuditGateEdge
    for edge in attached_audit_gate_edges(project=project):
        gated_upstream: list[CompiledObjectKey] = upstream.setdefault(edge.gated, [])
        if edge.read not in gated_upstream:
            gated_upstream.append(edge.read)

    hook_edge: HookReadEdge
    for hook_edge in hook_read_edges(project=project):
        hook_upstream: list[CompiledObjectKey] = upstream.setdefault(hook_edge.gated, [])
        if hook_edge.read not in hook_upstream:
            hook_upstream.append(hook_edge.read)

    return {k: tuple(v) for k, v in upstream.items()}


def build_execution_edge_origins(
    project: CompiledProject,
) -> dict[tuple[CompiledObjectKey, CompiledObjectKey], str]:
    """Return human-readable origins for execution edges injected beyond pure lineage."""

    origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str] = {}
    test: CompiledSqlTest
    for test in project.sql_tests:
        for target_key in test.scope_deps:
            origins[(target_key, test.key)] = (
                f"SQL test '{test.name}' runs before '{target_key.name}'"
            )
    lineage_upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_lineage_upstream_deps(project)
    )
    edge: AttachedAuditGateEdge
    for edge in attached_audit_gate_edges(project=project):
        if edge.read in lineage_upstream.get(edge.gated, ()):
            continue
        origins.setdefault(
            (edge.gated, edge.read),
            f"audit '{edge.audit_name}' on '{edge.target.name}' reads '{edge.read.name}'",
        )
    hook_edge: HookReadEdge
    for hook_edge in hook_read_edges(project=project):
        if hook_edge.read in lineage_upstream.get(hook_edge.gated, ()):
            continue
        origins.setdefault(
            (hook_edge.gated, hook_edge.read),
            f"{hook_edge.label} on '{hook_edge.gated.name}' reads '{hook_edge.read.name}'",
        )
    return origins


def _function_scope_deps_for_test(*, test: CompiledSqlTest) -> tuple[CompiledObjectKey, ...]:
    return tuple(
        scope_dep
        for scope_dep in test.scope_deps
        if scope_dep.resource_type in {CompiledResourceType.UDF, CompiledResourceType.TABLE_FN}
    )


def _function_deps_for_test(
    *,
    test: CompiledSqlTest,
    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]],
) -> tuple[CompiledObjectKey, ...]:
    deps: list[CompiledObjectKey] = []
    seen: set[CompiledObjectKey] = set()
    target_key: CompiledObjectKey
    for target_key in test.scope_deps:
        dep_key: CompiledObjectKey
        for dep_key in upstream.get(target_key, ()):
            if dep_key.resource_type not in {
                CompiledResourceType.UDF,
                CompiledResourceType.TABLE_FN,
            }:
                continue
            if dep_key in seen:
                continue
            seen.add(dep_key)
            deps.append(dep_key)
    return tuple(deps)


def build_downstream_deps(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return downstream edges keyed by upstream object key."""

    return invert_edges(edges=upstream, sort_key=_key_sort_key)


def topologically_order_keys(
    *,
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    injected_edge_origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str] | None = None,
) -> tuple[CompiledObjectKey, ...]:
    """Return all keys in stable dependency order using Kahn's algorithm."""

    node_keys: set[CompiledObjectKey] = set(upstream)
    dep_keys: tuple[CompiledObjectKey, ...]
    for dep_keys in upstream.values():
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            node_keys.add(dep_key)

    indegree: dict[CompiledObjectKey, int] = {key: 0 for key in node_keys}
    key: CompiledObjectKey
    for key, dep_keys in upstream.items():
        indegree[key] = len(dep_keys)

    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        upstream
    )
    ready: list[tuple[tuple[str, str], CompiledObjectKey]] = [
        (_key_sort_key(key), key) for key, count in indegree.items() if count == 0
    ]
    heapq.heapify(ready)
    ordered: list[CompiledObjectKey] = []

    while ready:
        current: CompiledObjectKey = heapq.heappop(ready)[1]
        ordered.append(current)
        downstream_key: CompiledObjectKey
        for downstream_key in downstream.get(current, ()):
            if downstream_key not in indegree:
                continue
            indegree[downstream_key] -= 1
            if indegree[downstream_key] == 0:
                heapq.heappush(ready, (_key_sort_key(downstream_key), downstream_key))

    if len(ordered) != len(node_keys):
        ordered_set: set[CompiledObjectKey] = set(ordered)
        cycle_keys: tuple[CompiledObjectKey, ...] = tuple(
            sorted(
                (key for key in node_keys if key not in ordered_set),
                key=_key_sort_key,
            )
        )
        cycle_names: str = ", ".join(f"{k.resource_type}:{k.name}" for k in cycle_keys)
        origin_notes: str = _cycle_origin_notes(
            cycle_keys=cycle_keys,
            upstream=upstream,
            injected_edge_origins=injected_edge_origins or {},
        )
        raise PlannerInputError(f"Dependency cycle detected involving: {cycle_names}{origin_notes}")

    return tuple(ordered)


def _cycle_origin_notes(
    *,
    cycle_keys: tuple[CompiledObjectKey, ...],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    injected_edge_origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str],
) -> str:
    """Describe injected (non-lineage) edges between cycle keys so users see the closure cause."""

    if not injected_edge_origins:
        return ""
    cycle_key_set: set[CompiledObjectKey] = set(cycle_keys)
    notes: list[str] = []
    key: CompiledObjectKey
    for key in cycle_keys:
        dep_key: CompiledObjectKey
        for dep_key in upstream.get(key, ()):
            if dep_key not in cycle_key_set:
                continue
            origin: str | None = injected_edge_origins.get((key, dep_key))
            if origin is not None:
                notes.append(origin)
    if not notes:
        return ""
    return " (via " + "; ".join(sorted(set(notes))) + ")"


def expand_upstream(
    *,
    key: CompiledObjectKey,
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive upstream keys reachable from the given key."""

    return transitive_closure(start=key, edges=upstream)


def expand_downstream(
    *,
    key: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive downstream keys reachable from the given key."""

    return transitive_closure(start=key, edges=downstream)


def find_path_keys(
    *,
    start: CompiledObjectKey,
    end: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all keys on directed paths from start to end."""

    on_path: frozenset[CompiledObjectKey] | None = path_nodes(
        start=start,
        end=end,
        downstream=downstream,
    )
    if on_path is None:
        raise PlannerInputError(
            f"'{end.resource_type}:{end.name}' is not downstream of "
            f"'{start.resource_type}:{start.name}'"
        )
    return on_path
