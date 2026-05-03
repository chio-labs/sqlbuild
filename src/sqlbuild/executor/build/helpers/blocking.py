"""Failure propagation and downstream blocking."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey


def block_downstream(
    *,
    failed_key: CompiledObjectKey,
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    selected_keys: frozenset[CompiledObjectKey],
    blocked_keys: set[CompiledObjectKey],
) -> None:
    """Add all selected transitive downstream keys to the blocked set."""

    stack: list[CompiledObjectKey] = [failed_key]
    visited: set[CompiledObjectKey] = set()
    while stack:
        current: CompiledObjectKey = stack.pop()
        neighbor: CompiledObjectKey
        for neighbor in downstream_deps.get(current, ()):
            if neighbor in visited:
                continue
            visited.add(neighbor)
            if neighbor in selected_keys:
                blocked_keys.add(neighbor)
            stack.append(neighbor)
