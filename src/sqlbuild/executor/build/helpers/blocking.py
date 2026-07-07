"""Failure propagation and downstream blocking."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey


def downstream_blocked_keys(
    *,
    failed_key: CompiledObjectKey,
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    selected_keys: frozenset[CompiledObjectKey],
) -> frozenset[CompiledObjectKey]:
    """Return all selected transitive downstream keys to block."""

    blocked: set[CompiledObjectKey] = set()
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
                blocked.add(neighbor)
            stack.append(neighbor)
    return frozenset(blocked)
