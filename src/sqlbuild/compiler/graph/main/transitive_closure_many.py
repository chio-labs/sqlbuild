"""Directed graph multi-start transitive closure entrypoint."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from sqlbuild.compiler.graph._helpers.algorithms import transitive_closure_many_impl


def transitive_closure_many[K](
    *, starts: Iterable[K], edges: Mapping[K, Iterable[K]], include_starts: bool
) -> frozenset[K]:
    """Return keys reachable from any start, plus the starts when requested."""

    return transitive_closure_many_impl(starts=starts, edges=edges, include_starts=include_starts)
