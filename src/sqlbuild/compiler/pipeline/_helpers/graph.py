"""Static compiled project graph helpers."""

from __future__ import annotations

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.graph.main._native_graph_from_views import native_graph_from_views
from sqlbuild.compiler.graph.main._native_project_graph import build_native_project_graph
from sqlbuild.compiler.graph.main.project_lineage_views import project_lineage_views
from sqlbuild.compiler.graph.models import LineageGraphViews
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection._graph_selection import resolve_graph_selection


def build_project_graph_impl(project: CompiledProject) -> ProjectGraph:
    """The project's natively built graph with its Python dict views."""

    lineage: LineageGraphViews = project_lineage_views(project)
    return ProjectGraph(
        project=project,
        upstream_deps=lineage.upstream_deps,
        downstream_deps=lineage.downstream_deps,
        tag_index=lineage.tag_index,
        path_index=lineage.path_index,
        all_keys=lineage.all_keys,
        native=build_native_project_graph(project),
    )


def select_project_graph_impl(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> frozenset[CompiledObjectKey]:
    """Resolve selectors on the graph's native handle, or on its dicts when built by hand."""

    native: _native.NativeProjectGraph = (
        graph.native
        if graph.native is not None
        else native_graph_from_views(
            all_keys=graph.all_keys,
            upstream=graph.upstream_deps,
            downstream=graph.downstream_deps,
            tag_index=graph.tag_index,
            path_index=graph.path_index,
        )
    )
    return resolve_graph_selection(graph=native, select=select, exclude=exclude)
