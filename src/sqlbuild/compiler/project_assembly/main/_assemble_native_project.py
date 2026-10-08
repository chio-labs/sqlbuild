"""Assemble the compiled project natively for the preview compiler engine."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs
from sqlbuild.compiler.lineage.types import ColumnLineageMode


def assemble_native_project(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile | None,
    skip_column_inference: bool,
    column_lineage_mode: ColumnLineageMode,
    analysis_cache_dir: Path | None,
    analysis_model_names: frozenset[str] | None,
) -> CompiledProject | None:
    """Return the compiled project, or None where Python must assemble it."""

    return None
