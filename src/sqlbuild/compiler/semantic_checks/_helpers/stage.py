"""The native semantic completion stage: type recovery, metadata checks, then completion."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.semantic_checks._helpers.completion import complete_native_diagnostics
from sqlbuild.compiler.semantic_checks._helpers.metadata import native_metadata_diagnostics
from sqlbuild.compiler.semantic_checks._helpers.payloads import session_fact_models
from sqlbuild.compiler.semantic_checks._helpers.type_recovery import recover_native_output_types
from sqlbuild.compiler.semantic_checks.constants import NATIVE_SEMANTIC_NO_CATALOG
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic


def completed_semantic_project(
    *,
    project: CompiledProject,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
    resource_sql_analysis: bool,
    session: Any | None,
) -> CompiledProject:
    """The completed project; a native internal failure raises `NativeCompilerError`."""

    if project.binding_catalog is None:
        raise _native.NativeCompilerError(NATIVE_SEMANTIC_NO_CATALOG)
    catalog: object = project.binding_catalog.native
    session_models: frozenset[str] = session_fact_models(project=project, session=session)
    recovered: CompiledProject = recover_native_output_types(
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
        project=replace(recovered, diagnostics=(*recovered.diagnostics, *metadata)),
        catalog=catalog,
        session=session,
        session_models=session_models,
    )
