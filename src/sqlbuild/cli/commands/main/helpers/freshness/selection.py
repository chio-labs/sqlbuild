"""Source freshness command selector helpers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.pipeline.models import ProjectGraph
from sqlbuild.compiler.planner.main.selection import resolve_project_selectors
from sqlbuild.compiler.planner.main.upstream import expand_project_upstream_keys


def resolve_freshness_source_names(
    *, graph: ProjectGraph, select: tuple[str, ...], exclude: tuple[str, ...]
) -> tuple[str, ...]:
    """Resolve CLI selectors to source names that should be observed."""

    selected_keys: frozenset[CompiledObjectKey]
    if select:
        selected_keys = resolve_project_selectors(
            select=select,
            exclude=(),
            all_keys=graph.all_keys,
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
            tag_index=graph.tag_index,
            path_index=graph.path_index,
        )
    else:
        selected_keys = frozenset(graph.all_keys.values())

    excluded_keys: frozenset[CompiledObjectKey] = (
        resolve_project_selectors(
            select=exclude,
            exclude=(),
            all_keys=graph.all_keys,
            upstream_deps=graph.upstream_deps,
            downstream_deps=graph.downstream_deps,
            tag_index=graph.tag_index,
            path_index=graph.path_index,
        )
        if exclude
        else frozenset()
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
