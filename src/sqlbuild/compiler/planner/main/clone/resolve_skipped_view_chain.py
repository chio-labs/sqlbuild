"""Deferred clone skipped-view entrypoint."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from sqlbuild.compiler.planner._helpers.graph.defer_clone import resolve_skipped_view_chain_impl


def resolve_skipped_view_chain[K](
    *,
    selected: frozenset[K],
    upstream: Mapping[K, tuple[K, ...]],
    is_clonable: Callable[[K], bool],
    is_view: Callable[[K], bool],
) -> frozenset[K]:
    """Return skipped view ancestors rebuilt over cloned boundaries."""

    return resolve_skipped_view_chain_impl(
        selected=selected,
        upstream=upstream,
        is_clonable=is_clonable,
        is_view=is_view,
    )
