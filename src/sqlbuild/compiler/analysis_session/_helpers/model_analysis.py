"""Start the native model analysis session, or hand the whole analysis to Python."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.session_rows import session_request
from sqlbuild.compiler.analysis_session.classes.native_model_analysis import NativeModelAnalysis
from sqlbuild.compiler.analysis_session.constants import (
    DEFERRAL_NO_CATALOG,
    DEFERRAL_NO_COMPACT_ANALYSIS,
    DEFERRAL_SESSION,
)
from sqlbuild.compiler.analysis_session.models import NativeModelAnalysisRequest
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import ModelSqlAnalysis


def native_model_analyses(
    *, request: NativeModelAnalysisRequest
) -> dict[str, ModelSqlAnalysis] | None:
    """Each model's analysis by name, or None (recorded) where Python must analyse."""

    catalog: Any = request.inference_profile.binding_catalog
    if not request.allow_compact_analysis:
        record_analysis_deferral(kind=DEFERRAL_NO_COMPACT_ANALYSIS)
        return None
    if catalog is None:
        record_analysis_deferral(kind=DEFERRAL_NO_CATALOG)
        return None
    if not request.model_inputs:
        return {}
    python: PythonModelAnalysis = PythonModelAnalysis(
        model_inputs=request.model_inputs,
        inference_profile=request.inference_profile,
        complete_binding_schemas=request.complete_binding_schemas,
    )
    row: tuple[object, ...] | None = session_request(
        request=request, python=python, schemas=catalog.schemas
    )
    session: _native.NativeModelAnalysisSession | None = (
        _native.start_model_analysis_session(catalog.native, row) if row is not None else None
    )
    if session is None:
        record_analysis_deferral(kind=DEFERRAL_SESSION)
        return None
    return NativeModelAnalysis(request=request, python=python, catalog=catalog).analyses(session)
