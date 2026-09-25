"""Pure model-name closure helpers for planner dependency graphs."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.graph.main.transitive_closure_many import transitive_closure_many


def build_downstream_model_name_closure(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    """Return model names reachable downstream from the given keys, including model roots."""

    return _build_model_name_closure(start_keys=start_keys, deps=downstream_deps)


def _build_model_name_closure(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    return frozenset(
        key.name
        for key in transitive_closure_many(starts=start_keys, edges=deps, include_starts=True)
        if key.resource_type == CompiledResourceType.MODEL
    )
