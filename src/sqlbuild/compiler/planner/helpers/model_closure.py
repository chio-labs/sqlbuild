"""Pure model-name closure helpers for planner dependency graphs."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType


def build_downstream_model_name_closure(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    """Return model names reachable downstream from the given keys, including model roots."""

    return _build_model_name_closure(start_keys=start_keys, deps=downstream_deps)


def build_upstream_model_name_closure(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    """Return model names reachable upstream from the given keys, including model roots."""

    return _build_model_name_closure(start_keys=start_keys, deps=upstream_deps)


def _build_model_name_closure(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    model_names: set[str] = set()
    visited: set[CompiledObjectKey] = set()
    stack: list[CompiledObjectKey] = list(start_keys)
    while stack:
        current: CompiledObjectKey = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        if current.resource_type == CompiledResourceType.MODEL:
            model_names.add(current.name)
        neighbor: CompiledObjectKey
        for neighbor in deps.get(current, ()):  # pragma: no branch
            stack.append(neighbor)
    return frozenset(model_names)
