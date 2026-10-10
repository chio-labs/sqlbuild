"""Build a project graph from an already-compiled project."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.pipeline._helpers.graph import build_project_graph_impl
from sqlbuild.compiler.pipeline.models import ProjectGraph


def build_project_graph_from_compiled_project(*, project: CompiledProject) -> ProjectGraph:
    """Build a static dependency graph for an already-compiled project."""

    return build_project_graph_impl(project)
