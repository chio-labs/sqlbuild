"""Complete semantic diagnostics natively for the preview compiler engine."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.sql_analysis.models import SqlBindingDiagnostic


def complete_native_semantic_diagnostics(
    *,
    project: CompiledProject,
    profile: ExpressionInferenceProfile,
    binding_results: dict[str, tuple[SqlBindingDiagnostic, ...]],
    resource_sql_analysis: bool,
) -> CompiledProject | None:
    """Return the completed project, or None where Python must complete its diagnostics."""

    return None
