"""Analyze model SQL natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    ModelAnalysisCaching,
    ModelSqlAnalysis,
)
from sqlbuild.compiler.lineage.types import InferredNullability


def analyze_native_model_sql(
    *,
    known_functions: tuple[str, ...],
    known_types: tuple[str, ...],
    model_inputs: tuple[CompileModelInput, ...],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    column_types_by_table: dict[str, dict[str, str]],
    inference_profile: ExpressionInferenceProfile,
    allow_compact_analysis: bool,
    rich_type_inference: bool,
    analysis_caching: ModelAnalysisCaching | None,
    complete_binding_schemas: dict[str, dict[str, str]],
) -> dict[str, ModelSqlAnalysis] | None:
    """Return each model's analysis by name, or None where Python must analyze the models."""

    return None
