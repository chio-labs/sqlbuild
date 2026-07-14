"""Model path selector index entrypoint."""

from sqlbuild.compiler.compile.models.core import CompiledObjectKey, CompiledProject
from sqlbuild.compiler.planner._helpers.graph.selector_indexes import build_model_path_index_impl


def build_model_path_index(project: CompiledProject) -> dict[CompiledObjectKey, str]:
    """Build a model-key-to-folder lookup from a compiled project."""

    return build_model_path_index_impl(project)
