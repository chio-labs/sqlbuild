"""Selector names of a native project graph."""

import sqlbuild._native as _native
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.graph._helpers.native_graph import lineage_graph_names_impl


def lineage_graph_names(graph: _native.NativeProjectGraph) -> dict[str, CompiledObjectKey]:
    """Return selector name to key, in project order, without the other graph views."""

    return lineage_graph_names_impl(graph)
