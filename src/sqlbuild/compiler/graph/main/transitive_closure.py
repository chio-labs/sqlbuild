"""Directed graph transitive closure entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.graph._helpers.algorithms import transitive_closure_impl


def transitive_closure[K](
    *, start: K, edges: Mapping[K, tuple[K, ...]], max_depth: int | None = None
) -> frozenset[K]:
    """Return all graph keys reachable from a starting key."""

    return transitive_closure_impl(start=start, edges=edges, max_depth=max_depth)
