"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile.models import (
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.lineage.types import ColumnLineageMode


def assemble_project(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile | None = None,
    skip_column_inference: bool = False,
    column_lineage_mode: ColumnLineageMode = ColumnLineageMode.FAST,
) -> CompiledProject:
    """Convert compile inputs into the planner-ready project view."""

    return assemble_compiled_project(
        inputs=inputs,
        inference_profile=inference_profile,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
    )
