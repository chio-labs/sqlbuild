"""Graph traversal helpers for planning over compiled project state."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledAudit,
    CompiledObjectKey,
    CompiledProject,
)
from sqlbuild.compiler.compile.models.sql_tests import CompiledSqlTest
from sqlbuild.compiler.compile.types import (
    AttachedAuditTargetKind,
    CompiledResourceType,
    SqlTestMode,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.shared.helpers.graph.algorithms import (
    invert_edges,
    path_nodes,
    transitive_closure,
)


def _key_sort_key(key: CompiledObjectKey) -> tuple[str, str]:
    return (key.resource_type, key.name)


def build_execution_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return EXECUTION-order edges: lineage plus audit scope-deps and woven SQL test nodes."""

    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    upstream.update({model.key: list(model.deps) for model in project.models})
    upstream.update({source.key: list(source.deps) for source in project.sources})
    upstream.update({seed.key: list(seed.deps) for seed in project.seeds})
    upstream.update({function.key: list(function.deps) for function in project.functions})

    audit: CompiledAudit
    for audit in project.audits:
        target_key: CompiledObjectKey | None = _attached_audit_target_key(audit=audit)
        if target_key is None or target_key not in upstream:
            continue
        dep_key: CompiledObjectKey
        for dep_key in audit.scope_deps:
            if dep_key == target_key or dep_key in upstream[target_key]:
                continue
            upstream[target_key].append(dep_key)

    test: CompiledSqlTest
    for test in project.sql_tests:
        if test.mode == SqlTestMode.TABLE_FN:
            upstream[test.key] = list(_function_scope_deps_for_test(test=test))
            continue
        upstream[test.key] = list(_function_deps_for_test(test=test, upstream=upstream))
        for target_key in test.scope_deps:
            if target_key in upstream:
                upstream[target_key].append(test.key)

    return {k: tuple(v) for k, v in upstream.items()}


def build_execution_edge_origins(
    project: CompiledProject,
) -> dict[tuple[CompiledObjectKey, CompiledObjectKey], str]:
    """Return human-readable origins for execution edges injected beyond pure lineage."""

    origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str] = {}
    audit: CompiledAudit
    for audit in project.audits:
        target_key: CompiledObjectKey | None = _attached_audit_target_key(audit=audit)
        if target_key is None:
            continue
        dep_key: CompiledObjectKey
        for dep_key in audit.scope_deps:
            if dep_key == target_key:
                continue
            origins[(target_key, dep_key)] = (
                f"audit '{audit.name}' on '{target_key.name}' reads '{dep_key.name}'"
            )
    test: CompiledSqlTest
    for test in project.sql_tests:
        for target_key in test.scope_deps:
            origins[(target_key, test.key)] = (
                f"SQL test '{test.name}' runs before '{target_key.name}'"
            )
    return origins


def _attached_audit_target_key(*, audit: CompiledAudit) -> CompiledObjectKey | None:
    if audit.attached_target_kind is None or audit.attached_target_name is None:
        return None
    target_kind: AttachedAuditTargetKind = AttachedAuditTargetKind(audit.attached_target_kind)
    if target_kind == AttachedAuditTargetKind.MODEL:
        return CompiledObjectKey(
            resource_type=CompiledResourceType.MODEL,
            name=audit.attached_target_name,
        )
    if target_kind == AttachedAuditTargetKind.SOURCE:
        return CompiledObjectKey(
            resource_type=CompiledResourceType.SOURCE,
            name=audit.attached_target_name,
        )
    return None


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

    return invert_edges(upstream, sort_key=_key_sort_key)


def topologically_order_keys(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    *,
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
    ready: list[CompiledObjectKey] = sorted(
        (key for key, count in indegree.items() if count == 0),
        key=_key_sort_key,
    )
    ordered: list[CompiledObjectKey] = []

    while ready:
        current: CompiledObjectKey = ready.pop(0)
        ordered.append(current)
        downstream_key: CompiledObjectKey
        for downstream_key in downstream.get(current, ()):
            if downstream_key not in indegree:
                continue
            indegree[downstream_key] -= 1
            if indegree[downstream_key] == 0:
                ready.append(downstream_key)
                ready.sort(key=_key_sort_key)

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
    key: CompiledObjectKey,
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive upstream keys reachable from the given key."""

    return transitive_closure(start=key, edges=upstream)


def expand_downstream(
    key: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive downstream keys reachable from the given key."""

    return transitive_closure(start=key, edges=downstream)


def find_path_keys(
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
