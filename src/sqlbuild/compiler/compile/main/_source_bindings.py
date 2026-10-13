"""Planner entrypoint for warehouse-backed semantic binding."""

from sqlbuild._native import source_binding_diagnostics
from sqlbuild.adapter.contract.models import ColumnInfo, ExpressionInferenceProfile
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompilerDiagnostic
from sqlbuild.compiler.compile.types import CompiledProjectView


def get_source_binding_diagnostics(
    *,
    project: CompiledProjectView,
    columns: dict[str, tuple[ColumnInfo, ...]],
    profile: ExpressionInferenceProfile,
    selected_keys: frozenset[CompiledObjectKey],
) -> tuple[CompilerDiagnostic, ...]:
    """Bind selected source readers to already-inspected warehouse columns."""
    return source_binding_diagnostics(
        project=project, columns=columns, profile=profile, selected_keys=selected_keys
    )
