"""Assemble planner-ready compiled project objects."""

from __future__ import annotations

from pathlib import Path

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
    analysis_cache_dir: Path | None = None,
    analysis_model_names: frozenset[str] | None = None,
) -> CompiledProject:
    """Convert compile inputs into the planner-ready project view."""

    return assemble_compiled_project(
        inputs=inputs,
        inference_profile=inference_profile,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        analysis_cache_dir=analysis_cache_dir,
        analysis_model_names=analysis_model_names,
    )
