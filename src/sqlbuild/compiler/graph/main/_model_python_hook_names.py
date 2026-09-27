"""Python hooks attached to one model."""

from __future__ import annotations

from sqlbuild.compiler.compile.models import CompiledModel
from sqlbuild.compiler.graph._helpers.hook_reads import model_python_hook_names_impl


def model_python_hook_names(*, model: CompiledModel) -> tuple[str, ...]:
    """Return the Python hooks attached to one model, in lifecycle order."""

    return model_python_hook_names_impl(model)
