"""Start the native model analysis session, or hand the whole analysis to Python."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.session_rows import (
    adapter_nullability_rules,
    session_request,
)
from sqlbuild.compiler.analysis_session.classes.native_model_analysis import NativeModelAnalysis
from sqlbuild.compiler.analysis_session.constants import (
    ADAPTER_NULLABILITY_CALLBACK,
    DEFERRAL_NO_CATALOG,
    DEFERRAL_NO_COMPACT_ANALYSIS,
    DEFERRAL_SESSION,
    NATIVE_ANALYSIS_STORE_FILE_NAME,
    NATIVE_ANALYSIS_STORE_VERSION,
)
from sqlbuild.compiler.analysis_session.models import (
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
)
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import AnalysisCacheContext, ModelSqlAnalysis
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.compiler.lineage.types import InferredNullability


def native_model_analyses(*, request: NativeModelAnalysisRequest) -> NativeModelAnalyses | None:
    """Each model's analysis by name and the finished session, or None (recorded) for Python."""

    catalog: Any = request.inference_profile.binding_catalog
    if not request.allow_compact_analysis:
        record_analysis_deferral(kind=DEFERRAL_NO_COMPACT_ANALYSIS)
        return None
    if catalog is None:
        record_analysis_deferral(kind=DEFERRAL_NO_CATALOG)
        return None
    if not request.model_inputs:
        return NativeModelAnalyses(analyses={}, session=None)
    python: PythonModelAnalysis = PythonModelAnalysis(
        model_inputs=request.model_inputs,
        inference_profile=request.inference_profile,
        complete_binding_schemas=request.complete_binding_schemas,
    )
    row: tuple[object, ...] | None = session_request(
        request=request, python=python, schemas=catalog.schemas
    )
    adapter_rules: dict[str, FunctionNullabilityRule] = adapter_nullability_rules(
        request.inference_profile
    )
    if adapter_rules:
        record_analysis_deferral(kind=ADAPTER_NULLABILITY_CALLBACK)
    session: _native.NativeModelAnalysisSession | None = (
        _native.start_model_analysis_session(
            catalog.native,
            row,
            None if adapter_rules else _analysis_store(request),
            (adapter_rules, InferredNullability) if adapter_rules else None,
        )
        if row is not None
        else None
    )
    if session is None:
        record_analysis_deferral(kind=DEFERRAL_SESSION)
        return None
    analyses: dict[str, ModelSqlAnalysis] | None = NativeModelAnalysis(
        request=request, python=python, catalog=catalog
    ).analyses(session)
    return None if analyses is None else NativeModelAnalyses(analyses=analyses, session=session)


def _analysis_store(request: NativeModelAnalysisRequest) -> tuple[str, str] | None:
    """The analysis store's path and environment, or None where Python bypasses its cache."""

    context: AnalysisCacheContext | None = request.analysis_cache
    if context is None:
        return None
    return (
        str(context.root / NATIVE_ANALYSIS_STORE_FILE_NAME),
        _native.content_digest(
            [
                NATIVE_ANALYSIS_STORE_VERSION,
                compiled_code_identity(),
                context.shared_fingerprint,
                context.signature_namespace,
            ]
        ),
    )
