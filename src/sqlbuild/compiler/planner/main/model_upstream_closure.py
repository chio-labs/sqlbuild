"""Public wrapper for upstream model-name closure."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.planner.helpers.graph.model_closure import build_upstream_model_name_closure


def build_upstream_model_names(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    return build_upstream_model_name_closure(
        start_keys=start_keys,
        upstream_deps=upstream_deps,
    )
