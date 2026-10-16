"""Failure propagation and downstream blocking."""

from __future__ import annotations

from sqlbuild._native import CompiledObjectKey, transitive_closure


def downstream_blocked_keys(
    *,
    failed_key: CompiledObjectKey,
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    selected_keys: frozenset[CompiledObjectKey],
) -> frozenset[CompiledObjectKey]:
    """Return all selected transitive downstream keys to block."""

    return transitive_closure(start=failed_key, edges=downstream_deps) & selected_keys
