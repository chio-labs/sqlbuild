"""Planner entrypoint for warehouse-backed semantic binding."""

from sqlbuild.adapter.contract.models import ColumnInfo, ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.assembly.source_bindings import (
    get_source_binding_diagnostics as _get_source_binding_diagnostics,
)
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompilerDiagnostic


def get_source_binding_diagnostics(
    *,
    project: CompiledProject,
    columns: dict[str, tuple[ColumnInfo, ...]],
    profile: ExpressionInferenceProfile,
    selected_keys: frozenset[CompiledObjectKey],
) -> tuple[CompilerDiagnostic, ...]:
    """Bind selected source readers to already-inspected warehouse columns."""
    return _get_source_binding_diagnostics(
        project=project, columns=columns, profile=profile, selected_keys=selected_keys
    )
