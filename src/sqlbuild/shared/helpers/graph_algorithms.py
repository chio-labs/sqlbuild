"""Dependency-neutral DAG algorithms shared by native planning and dbt interop."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any


def invert_edges[K](
    edges: Mapping[K, tuple[K, ...]],
    *,
    sort_key: Callable[[K], Any] | None = None,
) -> dict[K, tuple[K, ...]]:
    """Return reversed edges so an upstream map becomes a downstream map (or vice versa)."""

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


def transitive_closure[K](
    *, start: K, edges: Mapping[K, tuple[K, ...]], max_depth: int | None = None
) -> frozenset[K]:
    """Return all keys reachable from start via edges, excluding start itself."""

    visited: set[K] = set()
    frontier: list[tuple[K, int]] = [(start, 0)]
    while frontier:
        current: K
        depth: int
        current, depth = frontier.pop()
        if max_depth is not None and depth >= max_depth:
            continue
        neighbor: K
        for neighbor in edges.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            frontier.append((neighbor, depth + 1))
    return frozenset(visited)


def path_nodes[K](
    *,
    start: K,
    end: K,
    downstream: Mapping[K, tuple[K, ...]],
) -> frozenset[K] | None:
    """Return nodes on directed paths from start to end, or None when unreachable."""

    reachable_from_start: frozenset[K] = transitive_closure(start=start, edges=downstream)
    if end not in reachable_from_start:
        return None

    upstream: dict[K, tuple[K, ...]] = invert_edges(downstream)
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


def resolve_clone_boundary[K](
    *,
    selected: frozenset[K],
    upstream: Mapping[K, tuple[K, ...]],
    is_clonable: Callable[[K], bool],
    is_view: Callable[[K], bool],
) -> frozenset[K]:
    """Return the first non-view clonable ancestors that anchor data for selected nodes.

    Walks upstream from each selected node. Selected nodes and view nodes are walked
    through (views are recreated, not cloned) so the walk continues to the first
    clonable non-view ancestor, whose data anchors the recreated view chain. Other
    non-view nodes stop the walk: they are not cloned and their ancestors are not
    boundary candidates for this selection.
    """

    boundary: set[K] = set()
    visited: set[K] = set()

    def visit(node: K) -> None:
        if node in visited:
            return
        visited.add(node)
        upstream_node: K
        for upstream_node in upstream.get(node, ()):
            if upstream_node in selected or is_view(upstream_node):
                visit(upstream_node)
            elif is_clonable(upstream_node):
                boundary.add(upstream_node)

    selected_node: K
    for selected_node in selected:
        visit(selected_node)
    return frozenset(boundary)


def resolve_skipped_view_chain[K](
    *,
    selected: frozenset[K],
    upstream: Mapping[K, tuple[K, ...]],
    is_clonable: Callable[[K], bool],
    is_view: Callable[[K], bool],
) -> frozenset[K]:
    """Return out-of-selection view ancestors that must rebuild over cloned boundaries.

    These are the views the clone boundary walk skips; they cannot be cloned as data
    and must be rebuilt on top of the first cloned non-view ancestor.
    """

    views: set[K] = set()
    visited: set[K] = set()

    def visit(node: K) -> None:
        if node in visited:
            return
        visited.add(node)
        upstream_node: K
        for upstream_node in upstream.get(node, ()):
            if upstream_node in selected:
                visit(upstream_node)
            elif is_view(upstream_node):
                if is_clonable(upstream_node):
                    views.add(upstream_node)
                visit(upstream_node)

    selected_node: K
    for selected_node in selected:
        visit(selected_node)
    return frozenset(views)
