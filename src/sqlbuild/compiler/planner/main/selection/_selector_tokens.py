"""Public selector-token resolution entrypoint without required build resources."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.selectors import resolve_selector_tokens


def resolve_project_selector_tokens(
    *,
    selectors: tuple[str, ...],
    all_keys: dict[str, CompiledObjectKey],
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
    tag_index: dict[str, frozenset[CompiledObjectKey]],
    path_index: dict[CompiledObjectKey, str],
) -> frozenset[CompiledObjectKey]:
    """Resolve selector strings to the keys they match, without adding required build resources."""

    return resolve_selector_tokens(
        selectors=selectors,
        all_keys=all_keys,
        upstream=upstream_deps,
        downstream=downstream_deps,
        tag_index=tag_index,
        path_index=path_index,
    )
