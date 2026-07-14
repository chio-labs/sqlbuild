"""Compiled project upstream lineage entrypoint."""

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.graph.helpers.lineage import build_lineage_upstream_deps_impl


def build_lineage_upstream_deps(
    project: CompiledProject,
) -> dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]]:
    """Return pure data-flow upstream edges with SQL tests stripped."""

    return build_lineage_upstream_deps_impl(project)
