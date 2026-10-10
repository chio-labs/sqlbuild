"""Python dict views of a native project graph."""

import sqlbuild._native as _native
from sqlbuild.compiler.graph._helpers.native_graph import lineage_graph_views_impl
from sqlbuild.compiler.graph.models import LineageGraphViews


def lineage_graph_views(graph: _native.NativeProjectGraph) -> LineageGraphViews:
    """Return the graph's lineage edges and selector indexes as dicts, in project order."""

    return lineage_graph_views_impl(graph)
