"""Public upstream graph expansion entrypoint for planner consumers."""

from __future__ import annotations

from sqlbuild._native import transitive_closure
from sqlbuild.compiler.compile.models import CompiledObjectKey


def expand_project_upstream_keys(
    *,
    key: CompiledObjectKey,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return the upstream key closure for one compiled graph key."""

    return frozenset(transitive_closure(start=key, edges=upstream_deps))
