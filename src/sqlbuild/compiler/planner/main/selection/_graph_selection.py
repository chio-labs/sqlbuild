"""Public selector resolution over a native project graph."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.selectors import resolve_graph_selectors


def resolve_graph_selection(
    *,
    graph: _native.NativeProjectGraph,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
) -> frozenset[CompiledObjectKey]:
    """Resolve select/exclude strings natively, adding the functions selected models need."""

    return resolve_graph_selectors(graph=graph, select=select, exclude=exclude)
