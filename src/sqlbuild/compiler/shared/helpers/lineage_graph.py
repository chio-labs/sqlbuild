"""Shared LINEAGE graph builders: pure data-flow edges with SQL tests stripped."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import (
    CompiledFunction,
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSeed,
    CompiledSource,
)
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_lineage_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return LINEAGE edges: pure data flow with SQL tests stripped; selection resolves here."""

    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    model: CompiledModel
    for model in project.models:
        upstream[model.key] = model.deps
    source: CompiledSource
    for source in project.sources:
        upstream[source.key] = source.deps
    seed: CompiledSeed
    for seed in project.seeds:
        upstream[seed.key] = seed.deps
    function: CompiledFunction
    for function in project.functions:
        upstream[function.key] = function.deps
    return _filter_lineage_deps(upstream)


def build_lineage_downstream_deps(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return downstream edges keyed by upstream object key."""

    downstream: dict[CompiledObjectKey, list[CompiledObjectKey]] = {}
    for key in upstream:
        downstream.setdefault(key, [])
    for key, dep_keys in upstream.items():
        for dep_key in dep_keys:
            downstream.setdefault(dep_key, []).append(key)
    return {
        key: tuple(sorted(values, key=lambda obj: (str(obj.resource_type), obj.name)))
        for key, values in downstream.items()
    }


def _filter_lineage_deps(
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Remove virtual execution-order nodes that are not lineage dependencies."""

    filtered: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {}
    for key, deps in upstream_deps.items():
        if key.resource_type == CompiledResourceType.SQL_TEST:
            continue
        lineage_deps: list[CompiledObjectKey] = []
        for dep in deps:
            if dep.resource_type != CompiledResourceType.SQL_TEST:
                lineage_deps.append(dep)
        filtered[key] = tuple(lineage_deps)
    return filtered
