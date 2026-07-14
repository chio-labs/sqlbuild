"""Deferred clone graph traversal implementations."""

from __future__ import annotations

from collections.abc import Callable, Mapping


def resolve_clone_boundary_impl[K](
    *,
    selected: frozenset[K],
    upstream: Mapping[K, tuple[K, ...]],
    is_clonable: Callable[[K], bool],
    is_view: Callable[[K], bool],
) -> frozenset[K]:
    """Return non-view clonable ancestors anchoring selected nodes."""

    boundary: frozenset[K] = frozenset()
    visited: frozenset[K] = frozenset()

    def visit(
        *, node: K, visited: frozenset[K], boundary: frozenset[K]
    ) -> tuple[frozenset[K], frozenset[K]]:
        if node in visited:
            return visited, boundary
        visited = visited | {node}
        upstream_node: K
        for upstream_node in upstream.get(node, ()):
            if upstream_node in selected or is_view(upstream_node):
                visited, boundary = visit(node=upstream_node, visited=visited, boundary=boundary)
            elif is_clonable(upstream_node):
                boundary = boundary | {upstream_node}
        return visited, boundary

    selected_node: K
    for selected_node in selected:
        visited, boundary = visit(node=selected_node, visited=visited, boundary=boundary)
    return boundary


def resolve_skipped_view_chain_impl[K](
    *,
    selected: frozenset[K],
    upstream: Mapping[K, tuple[K, ...]],
    is_clonable: Callable[[K], bool],
    is_view: Callable[[K], bool],
) -> frozenset[K]:
    """Return skipped view ancestors rebuilt over cloned boundaries."""

    views: frozenset[K] = frozenset()
    visited: frozenset[K] = frozenset()

    def visit(
        *, node: K, visited: frozenset[K], views: frozenset[K]
    ) -> tuple[frozenset[K], frozenset[K]]:
        if node in visited:
            return visited, views
        visited = visited | {node}
        upstream_node: K
        for upstream_node in upstream.get(node, ()):
            if upstream_node in selected:
                visited, views = visit(node=upstream_node, visited=visited, views=views)
            elif is_view(upstream_node):
                if is_clonable(upstream_node):
                    views = views | {upstream_node}
                visited, views = visit(node=upstream_node, visited=visited, views=views)
        return visited, views

    selected_node: K
    for selected_node in selected:
        visited, views = visit(node=selected_node, visited=visited, views=views)
    return views
