"""Public wrapper for downstream model-name closure."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.model_closure import (
    build_downstream_model_name_closure,
)


def build_downstream_model_names(
    *,
    start_keys: tuple[CompiledObjectKey, ...],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> frozenset[str]:
    return build_downstream_model_name_closure(
        start_keys=start_keys,
        downstream_deps=downstream_deps,
    )
