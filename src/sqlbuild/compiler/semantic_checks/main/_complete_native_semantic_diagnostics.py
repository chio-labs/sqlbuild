"""Complete semantic diagnostics natively for the preview compiler engine."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.types import DiagnosticRow
from sqlbuild.compiler.compile.types import CompiledProjectView
from sqlbuild.compiler.semantic_checks._helpers.stage import completed_semantic_project


def complete_native_semantic_diagnostics(
    *,
    project: CompiledProjectView,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, list[DiagnosticRow]],
    resource_sql_analysis: bool,
    session: Any | None = None,
) -> CompiledProjectView:
    """The completed project; a native internal failure raises `NativeCompilerError`."""

    return completed_semantic_project(
        project=project,
        profile=profile,
        binding_results=binding_results,
        resource_sql_analysis=resource_sql_analysis,
        session=session,
    )
