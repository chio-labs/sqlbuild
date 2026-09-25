"""Rebind models to source columns already inspected by the planner."""

from __future__ import annotations

from sqlbuild.adapter.contract.models import ColumnInfo, ExpressionInferenceProfile
from sqlbuild.compiler.compile._helpers.analysis.compact import get_complete_schema_binding_request
from sqlbuild.compiler.compile._helpers.assembly.binding_positions import (
    get_authored_binding_position,
)
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlExpansion,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import BINDING_UNKNOWN_TABLE_INTERNAL_CODE
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult, SqlSchemaValidationRequest


def get_source_binding_diagnostics(
    *,
    project: CompiledProject,
    columns: dict[str, tuple[ColumnInfo, ...]],
    profile: ExpressionInferenceProfile,
    selected_keys: frozenset[CompiledObjectKey],
) -> tuple[CompilerDiagnostic, ...]:
    """Validate selected source readers without executing or inspecting warehouse SQL."""

    if not project.settings.sql_analysis or not columns:
        return ()
    shapes: dict[str, dict[str, str]] = semantic_shapes(project=project, profile=profile)
    for name, value in columns.items():
        if value:
            shapes[name] = {column.name: column.type for column in value}
    models: list[CompiledModel] = []
    for model in project.models:
        if model.key not in selected_keys or model.config.values.get("sql_analysis") is False:
            continue
        if any(
            reference.ref_kind == SqlReferenceKind.SOURCE and reference.ref_name in columns
            for reference in model.references
        ):
            models.append(model)
    requests: tuple[SqlSchemaValidationRequest, ...] = tuple(
        get_complete_schema_binding_request(
            known_functions=known_function_names(project.functions),
            known_types=known_declared_types(functions=project.functions, column_types=shapes),
            query_sql=cursor_intrinsics_analysis_sql(
                sql=model.query_sql, cursor_type=model.config.values.get("cursor_type")
            ),
            placeholders=_placeholders(model),
            dialect=profile.sql_analysis_dialect,
            binding_schema=shapes,
        )
        for model in models
    )
    results: tuple[SqlBindingResult, ...] = get_schema_validations(requests=requests)
    expansions: dict[str, CompiledSqlExpansion] = {
        path.stem: expansion for path, expansion in project.sql_expansions.items()
    }
    diagnostics: list[CompilerDiagnostic] = []
    for model, request, result in zip(models, requests, results, strict=True):
        for diagnostic in result.diagnostics:
            if diagnostic.code == BINDING_UNKNOWN_TABLE_INTERNAL_CODE:
                continue
            line: int | None
            column: int | None
            line, column = get_authored_binding_position(
                authored_sql=model.authored_sql,
                authored_query_sql=model.authored_query_sql,
                cleaned_sql=request.sql,
                diagnostic=diagnostic,
                expansion=expansions.get(model.name),
            )
            diagnostics.append(
                CompilerDiagnostic(
                    phase=DiagnosticPhase.COMPILE,
                    severity=DiagnosticSeverity(diagnostic.severity),
                    code=diagnostic.code,
                    message=diagnostic.message,
                    resource_type=CompiledResourceType.MODEL,
                    resource_name=model.name,
                    path=model.relative_path,
                    line=line,
                    column=column,
                )
            )
    return tuple(diagnostics)


def _placeholders(model: CompiledModel) -> dict[str, str] | None:
    values: object = model.config.values.get("placeholders")
    if isinstance(values, dict):
        return {str(key): str(value) for key, value in values.items()}
    return None
