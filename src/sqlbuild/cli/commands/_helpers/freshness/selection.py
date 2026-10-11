"""Source freshness command selector helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.main.project_graph_selection import select_project_graph
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection.upstream import expand_project_upstream_keys


def resolve_freshness_source_names(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve CLI selectors to source names that should be observed."""

    selected_keys: frozenset[CompiledObjectKey]
    if select:
        selected_keys = select_project_graph(graph=graph, select=select, exclude=())
    else:
        selected_keys = frozenset(graph.all_keys.values())

    excluded_keys: frozenset[CompiledObjectKey] = (
        select_project_graph(graph=graph, select=exclude, exclude=()) if exclude else frozenset()
    )
    source_names: frozenset[str] = _source_names_for_keys(graph=graph, keys=selected_keys)
    excluded_source_names: frozenset[str] = _source_names_for_keys(
        graph=graph,
        keys=excluded_keys,
    )
    return tuple(sorted(source_names - excluded_source_names))


def _source_names_for_keys(
    *, graph: ProjectGraph, keys: frozenset[CompiledObjectKey]
) -> frozenset[str]:
    source_names: set[str] = set()
    key: CompiledObjectKey
    for key in keys:
        if key.resource_type == CompiledResourceType.SOURCE:
            source_names.add(key.name)
        upstream_key: CompiledObjectKey
        for upstream_key in expand_project_upstream_keys(
            key=key,
            upstream_deps=graph.upstream_deps,
        ):
            if upstream_key.resource_type == CompiledResourceType.SOURCE:
                source_names.add(upstream_key.name)
    return frozenset(source_names)
