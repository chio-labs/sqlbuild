"""Lineage dicts of a compiled project."""

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.graph._helpers.native_graph import project_lineage_views_impl
from sqlbuild.compiler.graph.models import LineageGraphViews


def project_lineage_views(project: CompiledProject) -> LineageGraphViews:
    """Return the project's lineage edges and selector indexes, computed natively."""

    return project_lineage_views_impl(project)
