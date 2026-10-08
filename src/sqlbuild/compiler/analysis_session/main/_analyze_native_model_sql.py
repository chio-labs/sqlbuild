"""Analyze model SQL natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.compile.models import ModelSqlAnalysis


def analyze_native_model_sql(
    *, request: NativeModelAnalysisRequest
) -> dict[str, ModelSqlAnalysis] | None:
    """Return each model's analysis (and any pivot proof) by name, or None to defer to Python."""

    return None
