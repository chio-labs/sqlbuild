"""Analyze model SQL natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.compiler.analysis_session._helpers.model_analysis import native_model_analyses
from sqlbuild.compiler.analysis_session.models import (
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
)


def analyze_native_model_sql(*, request: NativeModelAnalysisRequest) -> NativeModelAnalyses:
    """Return each model's analysis (and pivot proof) and the session."""

    return native_model_analyses(request=request)
