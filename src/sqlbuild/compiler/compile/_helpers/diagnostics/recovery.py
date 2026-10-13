"""Complete semantic diagnostics: type recovery, metadata checks, recovery and explanations."""

from __future__ import annotations

from typing import Any

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.types import DiagnosticRow
from sqlbuild.compiler.compile.types import CompiledProjectView


def complete_semantic_diagnostics(
    *,
    project: CompiledProjectView,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, list[DiagnosticRow]],
    resource_sql_analysis: bool = True,
    native_session: Any | None = None,
) -> CompiledProjectView:
    """Recover type facts before metadata checks, then explain retained root diagnostics."""

    return _native.complete_semantic_project(
        project=project,
        profile=profile,
        binding_results=binding_results,
        resource_sql_analysis=resource_sql_analysis,
        session=native_session,
    )
