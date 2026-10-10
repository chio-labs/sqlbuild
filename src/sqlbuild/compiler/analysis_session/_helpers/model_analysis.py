"""Run the native model analysis session."""

from __future__ import annotations

from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.adapter.contract.types import FunctionNullabilityRule
from sqlbuild.compiler.analysis_session._helpers.deferral_records import record_analysis_deferral
from sqlbuild.compiler.analysis_session._helpers.profile_rows import adapter_nullability_rules
from sqlbuild.compiler.analysis_session._helpers.session_rows import session_request
from sqlbuild.compiler.analysis_session.classes.native_model_analysis import NativeModelAnalysis
from sqlbuild.compiler.analysis_session.constants import (
    ADAPTER_NULLABILITY_CALLBACK,
    NATIVE_ANALYSIS_STORE_FILE_NAME,
    NATIVE_ANALYSIS_STORE_VERSION,
)
from sqlbuild.compiler.analysis_session.models import (
    NativeModelAnalyses,
    NativeModelAnalysisRequest,
)
from sqlbuild.compiler.compile.classes.python_model_analysis import PythonModelAnalysis
from sqlbuild.compiler.compile.models import AnalysisCacheContext
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.compiler.lineage.types import InferredNullability


def native_model_analyses(*, request: NativeModelAnalysisRequest) -> NativeModelAnalyses:
    """Each model's analysis by name and the finished session; a native internal failure raises."""

    if not request.model_inputs:
        return NativeModelAnalyses(analyses={}, session=None)
    catalog: Any = cast(Any, request.inference_profile.binding_catalog)
    python: PythonModelAnalysis = PythonModelAnalysis(
        model_inputs=request.model_inputs,
        inference_profile=request.inference_profile,
        complete_binding_schemas=request.complete_binding_schemas,
    )
    adapter_rules: dict[str, FunctionNullabilityRule] = adapter_nullability_rules(
        request.inference_profile
    )
    if adapter_rules:
        record_analysis_deferral(kind=ADAPTER_NULLABILITY_CALLBACK)
    session: _native.NativeModelAnalysisSession = _native.start_model_analysis_session(
        catalog.native,
        session_request(request=request, python=python, schemas=catalog.schemas),
        None if adapter_rules else _analysis_store(request),
        (adapter_rules, InferredNullability) if adapter_rules else None,
    )
    return NativeModelAnalyses(
        analyses=NativeModelAnalysis(request=request, python=python, catalog=catalog).analyses(
            session
        ),
        session=session,
    )


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
