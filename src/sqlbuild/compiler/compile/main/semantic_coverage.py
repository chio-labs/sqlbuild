"""Public semantic-check coverage report."""

from sqlbuild.compiler.compile._helpers.assembly.semantic_coverage import semantic_coverage
from sqlbuild.compiler.compile.types import CompiledProjectView


def get_semantic_coverage(project: CompiledProjectView) -> dict[str, tuple[str, ...]]:
    """Return per-model partial-check reasons."""
    return semantic_coverage(project)
