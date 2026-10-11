"""A compiled project with some fields changed, natively when its owner holds it."""

from typing import Any

from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.compiled_project._helpers.model_updates import project_with_impl


def project_with(*, project: CompiledProjectView, **changes: Any) -> CompiledProjectView:
    """The project with `changes`; a native view shares its owner's models."""

    return project_with_impl(project=project, **changes)
