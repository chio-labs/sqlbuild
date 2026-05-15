"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.helpers.assembly import assemble_compiled_project
from sqlbuild.compiler.compile.models.core import (
    CompiledProject,
    CompileProjectInputs,
)


def assemble_project(
    inputs: CompileProjectInputs,
    *,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> CompiledProject:
    """Convert compile inputs into the planner-ready project view."""

    return assemble_compiled_project(inputs, inference_profile=inference_profile)
