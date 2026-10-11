"""Selector resolution over a project graph."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.pipeline._helpers.graph import select_project_graph_impl
from sqlbuild.compiler.pipeline.models import ProjectGraph


def select_project_graph(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> frozenset[CompiledObjectKey]:
    """Resolve `--select`/`--exclude` on the graph, adding the functions they need to build."""

    return select_project_graph_impl(graph=graph, select=select, exclude=exclude)
