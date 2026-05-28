"""Public entrypoint for build resource expansion."""

from __future__ import annotations

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.planner.helpers.selectors import (
    expand_required_build_resources as _expand_required_build_resources,
)


def expand_build_resource_selection(
    *,
    selected_keys: frozenset[CompiledObjectKey],
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    include_upstream_functions: bool = True,
    include_upstream_seeds: bool = False,
    include_downstream_functions: bool = False,
) -> frozenset[CompiledObjectKey]:
    """Add non-model resources needed to build a coherent selected model scope."""

    return _expand_required_build_resources(
        selected_keys=selected_keys,
        upstream=upstream,
        downstream=downstream,
        include_upstream_functions=include_upstream_functions,
        include_upstream_seeds=include_upstream_seeds,
        include_downstream_functions=include_downstream_functions,
    )
