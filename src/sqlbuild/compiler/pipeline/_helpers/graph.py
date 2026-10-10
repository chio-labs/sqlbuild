"""Static compiled project graph helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection._graph_selection import resolve_graph_selection


def build_project_graph_impl(project: CompiledProject) -> ProjectGraph:
    """The project's natively held graph; dict views are built only when a boundary reads them."""

    return ProjectGraph(project=project, native=project.lineage_graph)


def select_project_graph_impl(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> frozenset[CompiledObjectKey]:
    """Resolve selectors on the graph's native handle."""

    return resolve_graph_selection(graph=graph.native, select=select, exclude=exclude)
