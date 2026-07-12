"""Directed graph path-node entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.graph.helpers.algorithms import path_nodes_impl


def path_nodes[K](
    *, start: K, end: K, downstream: Mapping[K, tuple[K, ...]]
) -> frozenset[K] | None:
    """Return keys on directed paths between two endpoints."""

    return path_nodes_impl(start=start, end=end, downstream=downstream)
