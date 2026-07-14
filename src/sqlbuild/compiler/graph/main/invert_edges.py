"""Directed graph edge inversion entrypoint."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlbuild.compiler.graph._helpers.algorithms import invert_edges_impl


def invert_edges[K](
    *, edges: Mapping[K, tuple[K, ...]], sort_key: Callable[[K], Any] | None = None
) -> dict[K, tuple[K, ...]]:
    """Return reversed directed graph edges."""

    return invert_edges_impl(edges=edges, sort_key=sort_key)
