"""Selector resolution over a project graph."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection._graph_selection import resolve_graph_selection


def select_project_graph(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> frozenset[CompiledObjectKey]:
    """Resolve `--select`/`--exclude` on the graph, adding the functions they need to build."""

    return resolve_graph_selection(graph=graph.native, select=select, exclude=exclude)
