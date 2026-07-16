"""Public upstream graph expansion entrypoint for planner consumers."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.core import expand_upstream


def expand_project_upstream_keys(
    *,
    key: CompiledObjectKey,
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[CompiledObjectKey]:
    """Return the upstream key closure for one compiled graph key."""

    return frozenset(expand_upstream(key=key, upstream=upstream_deps))
