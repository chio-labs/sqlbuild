"""The native semantic completion stage: type recovery, metadata checks, then completion."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.types import DiagnosticRow
from sqlbuild.compiler.compile.models import CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.compiled_project.main.project_with import project_with
from sqlbuild.compiler.semantic_checks._helpers.completion import complete_native_diagnostics
from sqlbuild.compiler.semantic_checks._helpers.metadata import native_metadata_diagnostics
from sqlbuild.compiler.semantic_checks._helpers.payloads import session_fact_models
from sqlbuild.compiler.semantic_checks._helpers.type_recovery import recover_native_output_types
from sqlbuild.compiler.semantic_checks.constants import NATIVE_SEMANTIC_NO_CATALOG


def completed_semantic_project(
    *,
    project: CompiledProjectView,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, list[DiagnosticRow]],
    resource_sql_analysis: bool,
    session: Any | None,
) -> CompiledProjectView:
    """The completed project; a native internal failure raises `NativeCompilerError`."""

    if project.binding_catalog is None:
        raise _native.NativeCompilerError(NATIVE_SEMANTIC_NO_CATALOG)
    catalog: object = project.binding_catalog.native
    session_models: frozenset[str] = session_fact_models(project=project, session=session)
    recovered: CompiledProjectView = recover_native_output_types(
        project=project,
        binding_results=binding_results,
        catalog=catalog,
        session=session,
        session_models=session_models,
    )
    metadata: tuple[CompilerDiagnostic, ...] = native_metadata_diagnostics(
        project=recovered,
        profile=profile,
        resource_sql_analysis=resource_sql_analysis,
        catalog=catalog,
    )
    return complete_native_diagnostics(
        project=project_with(project=recovered, diagnostics=(*recovered.diagnostics, *metadata)),
        catalog=catalog,
        session=session,
        session_models=session_models,
    )
