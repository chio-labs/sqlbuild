"""Compiled project downstream lineage entrypoint."""

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.graph.helpers.lineage import build_lineage_downstream_deps_impl


def build_lineage_downstream_deps(
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]],
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return downstream edges keyed by upstream object key."""

    return build_lineage_downstream_deps_impl(upstream)
