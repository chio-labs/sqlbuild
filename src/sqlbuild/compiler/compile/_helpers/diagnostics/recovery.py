"""Complete semantic diagnostics: type recovery, metadata checks, recovery and explanations."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.types import DiagnosticRow
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.semantic_checks.main._complete_native_semantic_diagnostics import (
    complete_native_semantic_diagnostics,
)


def complete_semantic_diagnostics(
    *,
    project: CompiledProjectView,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, list[DiagnosticRow]],
    resource_sql_analysis: bool = True,
    native_session: Any | None = None,
) -> CompiledProjectView:
    """Recover type facts before metadata checks, then explain retained root diagnostics."""

    return complete_native_semantic_diagnostics(
        project=project,
        profile=profile,
        binding_results=binding_results,
        resource_sql_analysis=resource_sql_analysis,
        session=native_session,
    )
