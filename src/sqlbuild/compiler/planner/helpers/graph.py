"""Graph traversal helpers for planning over compiled project state."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
)


def build_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return upstream edges keyed by object key (what each node depends on).

    SQL tests are virtual nodes with no warehouse deps. Each test is placed
    before its target models by adding the test key as an upstream dep of
    each target model key.
    """

    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    upstream.update({model.key: list(model.deps) for model in project.models})
    upstream.update({source.key: list(source.deps) for source in project.sources})
    upstream.update({seed.key: list(seed.deps) for seed in project.seeds})
    upstream.update({function.key: list(function.deps) for function in project.functions})

    test: CompiledSqlTest
    for test in project.sql_tests:
        upstream[test.key] = []
        target_key: CompiledObjectKey
        for target_key in test.scope_deps:
            if target_key in upstream:
                upstream[target_key].append(test.key)

    return {k: tuple(v) for k, v in upstream.items()}


def build_downstream_deps(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return downstream edges keyed by upstream object key."""

    downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    key: CompiledObjectKey
    for key in upstream:
        downstream.setdefault(key, [])
    dep_keys: tuple[CompiledObjectKey, ...]
    for key, dep_keys in upstream.items():
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            downstream.setdefault(dep_key, []).append(key)
    return {
        k: tuple(sorted(v, key=lambda obj: (obj.resource_type, obj.name)))
        for k, v in downstream.items()
    }


def topologically_order_keys(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
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
        key=lambda obj: (obj.resource_type, obj.name),
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
                ready.sort(key=lambda obj: (obj.resource_type, obj.name))

    if len(ordered) != len(node_keys):
        ordered_set: set[CompiledObjectKey] = set(ordered)
        cycle_keys: tuple[CompiledObjectKey, ...] = tuple(
            sorted(
                (key for key in node_keys if key not in ordered_set),
                key=lambda obj: (obj.resource_type, obj.name),
            )
        )
        cycle_names: str = ", ".join(f"{k.resource_type}:{k.name}" for k in cycle_keys)
        raise ValueError(f"Dependency cycle detected involving: {cycle_names}")

    return tuple(ordered)


def expand_upstream(
    key: CompiledObjectKey,
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive upstream keys reachable from the given key."""

    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        neighbor: CompiledObjectKey
        for neighbor in upstream.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)


def expand_downstream(
    key: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all transitive downstream keys reachable from the given key."""

    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [key]
    while stack:
        current: CompiledObjectKey = stack.pop()
        neighbor: CompiledObjectKey
        for neighbor in downstream.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            stack.append(neighbor)
    return frozenset(visited)


def find_path_keys(
    start: CompiledObjectKey,
    end: CompiledObjectKey,
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return all keys on directed paths from start to end (inclusive).

    Raises ValueError if end is not downstream of start.
    """

    reachable_from_start: frozenset[CompiledObjectKey] = expand_downstream(start, downstream)
    if end not in reachable_from_start:
        raise ValueError(
            f"'{end.resource_type}:{end.name}' is not downstream of "
            f"'{start.resource_type}:{start.name}'"
        )

    upstream_from_end: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = [end]
    upstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    key: CompiledObjectKey
    dep_keys: tuple[CompiledObjectKey, ...]
    for key, dep_keys in downstream.items():
        dep_key: CompiledObjectKey
        for dep_key in dep_keys:
            upstream.setdefault(dep_key, []).append(key)

    while stack:
        current: CompiledObjectKey = stack.pop()
        if current in upstream_from_end:
            continue
        upstream_from_end.add(current)
        parent: CompiledObjectKey
        for parent in upstream.get(current, ()):
            if parent in reachable_from_start or parent == start:
                stack.append(parent)

    on_path: frozenset[CompiledObjectKey] = frozenset(
        reachable_from_start & upstream_from_end | {start, end}
    )
    return on_path
