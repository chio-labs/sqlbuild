"""Public selector-resolution entrypoints for planner consumers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.selectors import resolve_selectors


def resolve_project_selectors(
    *,
    select: tuple[str, ...],
    exclude: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Resolve model/source/seed/function selectors against a compiled graph."""

    return resolve_selectors(
        select=select,
        exclude=exclude,
        all_keys=all_keys,
        upstream=upstream_deps,
        downstream=downstream_deps,
        tag_index=tag_index,
        path_index=path_index,
    )
