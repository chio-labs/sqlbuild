"""Deferred clone boundary entrypoint."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.compiler.planner._helpers.graph.defer_clone import resolve_clone_boundary_impl


def resolve_clone_boundary[K](
    *,
    selected: frozenset[K],
    upstream: Mapping[K, tuple[K, ...]],
    is_clonable: Callable[[K], bool],
    is_view: Callable[[K], bool],
) -> frozenset[K]:
    """Return non-view clonable ancestors anchoring selected nodes."""

    return resolve_clone_boundary_impl(
        selected=selected,
        upstream=upstream,
        is_clonable=is_clonable,
        is_view=is_view,
    )
