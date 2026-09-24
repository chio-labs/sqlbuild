"""Compiler graph algorithm implementations."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from typing import Any


def invert_edges_impl[K](
    *,
    edges: Mapping[K, tuple[K, ...]],
    sort_key: Callable[[K], Any] | None = None,
) -> dict[K, tuple[K, ...]]:
    """Return reversed directed graph edges."""

    inverted: dict[K, list[K]] = {key: [] for key in edges}
    source: K
    targets: tuple[K, ...]
    for source, targets in edges.items():
        target: K
        for target in targets:
            inverted.setdefault(target, []).append(source)
    if sort_key is None:
        return {key: tuple(values) for key, values in inverted.items()}
    return {key: tuple(sorted(values, key=sort_key)) for key, values in inverted.items()}


def transitive_closure_impl[K](
    *, start: K, edges: Mapping[K, tuple[K, ...]], max_depth: int | None = None
) -> frozenset[K]:
    """Return all graph keys reachable from a starting key."""

    return transitive_closure_many_impl(
        starts=(start,), edges=edges, include_starts=False, max_depth=max_depth
    )


def transitive_closure_many_impl[K](
    *,
    starts: Iterable[K],
    edges: Mapping[K, Iterable[K]],
    include_starts: bool,
    max_depth: int | None = None,
) -> frozenset[K]:
    """Return graph keys within an optional edge distance of any starting key."""

    start_keys: tuple[K, ...] = tuple(starts)
    visited: set[K] = set(start_keys) if include_starts else set()
    frontier: deque[tuple[K, int]] = deque((start_key, 0) for start_key in start_keys)
    while frontier:
        current: K
        depth: int
        current, depth = frontier.popleft()
        if max_depth is not None and depth >= max_depth:
            continue
        neighbor: K
        for neighbor in edges.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
    return frozenset(visited)


def path_nodes_impl[K](
    *, start: K, end: K, downstream: Mapping[K, tuple[K, ...]]
) -> frozenset[K] | None:
    """Return keys on directed paths between two endpoints."""

    reachable_from_start: frozenset[K] = transitive_closure_impl(start=start, edges=downstream)
    if end not in reachable_from_start:
        return None
    upstream: dict[K, tuple[K, ...]] = invert_edges_impl(edges=downstream)
    upstream_from_end: set[K] = set()
    stack: list[K] = [end]
    while stack:
        current: K = stack.pop()
        if current in upstream_from_end:
            continue
        upstream_from_end.add(current)
        parent: K
        for parent in upstream.get(current, ()):
            if parent in reachable_from_start or parent == start:
                stack.append(parent)
    return frozenset(reachable_from_start & upstream_from_end | {start, end})
