"""Lineage dicts of a compiled project."""

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.graph._helpers.native_graph import project_lineage_views_impl
from sqlbuild.compiler.graph.models import LineageGraphViews


def project_lineage_views(project: CompiledProjectView) -> LineageGraphViews:
    """Return the project's lineage edges and selector indexes, computed natively."""

    return project_lineage_views_impl(project)
