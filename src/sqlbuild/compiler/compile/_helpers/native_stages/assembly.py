"""Hand compiled-project assembly and model analysis to their native stages when enabled."""

from __future__ import annotations

from functools import partial
from pathlib import Path

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._analyze_native_model_sql import (
    analyze_native_model_sql,
)
from sqlbuild.compiler.compile.models import CompiledProject, CompileProjectInputs, ModelSqlAnalysis
from sqlbuild.compiler.frontier.main.native_stage_enabled import native_stage_enabled
from sqlbuild.compiler.frontier.types import NativeStage
from sqlbuild.compiler.lineage.types import ColumnLineageMode
from sqlbuild.compiler.project_assembly.main._assemble_native_project import (
    assemble_native_project,
)


def assemble_project_by_engine(
    *,
    inputs: CompileProjectInputs,
    inference_profile: ExpressionInferenceProfile | None,
    skip_column_inference: bool,
    column_lineage_mode: ColumnLineageMode,
    analysis_cache_dir: Path | None,
    analysis_model_names: frozenset[str] | None,
) -> CompiledProject | None:
    """Return the natively assembled project, or None where Python must assemble it."""

    if not native_stage_enabled(NativeStage.PROJECT_ASSEMBLY):
        return None
    return assemble_native_project(
        inputs=inputs,
        inference_profile=inference_profile,
        skip_column_inference=skip_column_inference,
        column_lineage_mode=column_lineage_mode,
        analysis_cache_dir=analysis_cache_dir,
        analysis_model_names=analysis_model_names,
    )


def analyze_model_sql_by_engine(
    *, python_analysis: partial[dict[str, ModelSqlAnalysis]]
) -> dict[str, ModelSqlAnalysis]:
    """Analyze models natively with the Python analysis's arguments, or run the Python analysis."""

    if native_stage_enabled(NativeStage.MODEL_ANALYSIS):
        native_analyses: dict[str, ModelSqlAnalysis] | None = analyze_native_model_sql(
            **python_analysis.keywords
        )
        if native_analyses is not None:
            return native_analyses
    return python_analysis()
