"""Model tag selector index entrypoint."""

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.graph.selector_indexes import build_model_tag_index_impl


def build_model_tag_index(project: CompiledProject) -> dict[str, frozenset[CompiledObjectKey]]:
    """Build a tag-to-model-key lookup from a compiled project."""

    return build_model_tag_index_impl(project)
