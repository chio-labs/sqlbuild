"""Planner helpers for source auto-load selection."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType


def managed_source_upstream_keys(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    project: CompiledProject,
) -> frozenset[CompiledObjectKey]:
    """Return selected managed source keys reachable from the current selection."""

    managed_source_names: frozenset[str] = frozenset(
        source.name for source in project.sources if source.source_entry.loader is not None
    )
    direct_upstream_sources: set[CompiledObjectKey] = set()
    selected_key: CompiledObjectKey
    for selected_key in selected_keys:
        if selected_key.resource_type != CompiledResourceType.MODEL:
            continue
        upstream_key: CompiledObjectKey
        for upstream_key in upstream_deps.get(selected_key, ()):
            if upstream_key.resource_type == CompiledResourceType.SOURCE:
                direct_upstream_sources.add(upstream_key)
    return frozenset(key for key in direct_upstream_sources if key.name in managed_source_names)
