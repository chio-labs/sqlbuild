"""Check column-bearing model metadata against authoritative output shapes."""

from __future__ import annotations

import re
from functools import lru_cache

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.compiler.analysis_session.main._infer_native_query_columns import (
    infer_native_query_columns,
)
from sqlbuild.compiler.analysis_session.models import NativeColumnQuery, NativeQueryColumns
from sqlbuild.compiler.compile._helpers.assembly.native_declarations import (
    known_declared_types,
    known_function_names,
)
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.sql_analysis.constants import BINDING_UNKNOWN_TABLE_INTERNAL_CODE
from sqlbuild.compiler.sql_analysis.main._resolve_binding_column import resolve_binding_column
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult, SqlSchemaValidationRequest
from sqlbuild.spec.contracts.models import SchemaAuditInstance

_EXPRESSION_AUDIT: str = "expression_is_true"
_RELATIONSHIPS_AUDIT: str = "relationships"
_ACCEPTED_VALUES_AUDIT: str = "accepted_values"


def _audit_errors(
    *,
    model: CompiledModel,
    project: CompiledProject,
    shape: dict[str, str],
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    if model.schema_entry is None:
        return ()
    diagnostics: list[CompilerDiagnostic] = []
    attached: list[tuple[str | None, SchemaAuditInstance]] = [
        (None, audit) for audit in model.schema_entry.audits
    ]
    for schema_column in model.schema_entry.columns:
        attached.extend((schema_column.name, audit) for audit in schema_column.audits)
    for column, audit in attached:
        arguments: dict[str, object] = audit.arguments
        if audit.definition_name == _EXPRESSION_AUDIT:
            expression: object = arguments.get("expression")
            if isinstance(expression, str):
                result: SqlBindingResult = get_schema_validations(
                    requests=(
                        SqlSchemaValidationRequest(
                            sql=f"SELECT * FROM output WHERE {expression}",
                            dialect=profile.sql_analysis_dialect,
                            schema={"output": shape},
                            known_functions=known_function_names(project.functions),
                            catalog=project.binding_catalog,
                            quoted_identifiers_ignore_case=profile.quoted_identifiers_ignore_case,
                            known_types=known_declared_types(
                                functions=project.functions, column_types=shapes
                            ),
                        ),
                    )
                )[0]
                diagnostics.extend(
                    _model_error(
                        model=model,
                        code=diagnostic.code,
                        name=expression,
                        message=f"expression_is_true: {diagnostic.message}",
                        severity=DiagnosticSeverity(diagnostic.severity),
                    )
                    for diagnostic in result.diagnostics
                    if diagnostic.code != BINDING_UNKNOWN_TABLE_INTERNAL_CODE
                )
        elif audit.definition_name == _RELATIONSHIPS_AUDIT and column:
            target: str = str(arguments.get("to", ""))
            match: re.Match[str] | None = re.search(
                r"__(?:ref|source|seed)\([\'\"]([^\'\"]+)[\'\"]\)", target
            )
            target_shape: dict[str, str] | None = shapes.get(match.group(1) if match else target)
            field: str = str(arguments.get("field", ""))
            resolved_field: str | None = resolve_binding_column(
                name=field,
                columns=target_shape or {},
                dialect=profile.sql_analysis_dialect,
                ignore_quoted_case=profile.quoted_identifiers_ignore_case,
            )
            if target_shape and resolved_field is None:
                diagnostics.append(
                    _model_error(
                        model=model,
                        code="B300",
                        name=field,
                        message=f"relationships target has no column '{field}'",
                    )
                )
            elif target_shape is not None and resolved_field is not None and column in shape:
                diagnostics.extend(
                    _model_error(
                        model=model,
                        code="B301"
                        if diagnostic.severity == DiagnosticSeverity.ERROR
                        else diagnostic.code,
                        name=column,
                        message=f"relationships: {diagnostic.message}",
                        severity=DiagnosticSeverity(diagnostic.severity),
                    )
                    for diagnostic in _comparison_result(
                        left=shape[column],
                        right=target_shape[resolved_field],
                        dialect=profile.sql_analysis_dialect,
                    ).diagnostics
                )
        elif audit.definition_name == _ACCEPTED_VALUES_AUDIT and column in shape:
            values: object = arguments.get("values")
            if isinstance(values, (list, tuple)):
                literals: list[str | None] = [_audit_literal(value) for value in values]
                if literals and all(literal is not None for literal in literals):
                    result = _accepted_values_result(
                        literals=tuple(str(value) for value in literals),
                        dialect=profile.sql_analysis_dialect,
                        column_type=shape[column],
                    )
                    diagnostics.extend(
                        _model_error(
                            model=model,
                            code="B301" if item.severity == DiagnosticSeverity.ERROR else item.code,
                            name=column,
                            message=f"accepted_values: {item.message}",
                            severity=DiagnosticSeverity(item.severity),
                        )
                        for item in result.diagnostics
                    )
    return tuple(diagnostics)


@lru_cache(maxsize=256)
def _comparison_result(*, left: str, right: str, dialect: str | None) -> SqlBindingResult:
    return get_schema_validations(
        requests=(
            SqlSchemaValidationRequest(
                sql="SELECT lhs.value = rhs.value FROM lhs CROSS JOIN rhs",
                dialect=dialect,
                schema={"lhs": {"value": left}, "rhs": {"value": right}},
            ),
        )
    )[0]


def _audit_literal(value: object) -> str | None:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


@lru_cache(maxsize=256)
def _accepted_values_result(
    *, literals: tuple[str, ...], dialect: str | None, column_type: str
) -> SqlBindingResult:
    return get_schema_validations(
        requests=(
            SqlSchemaValidationRequest(
                sql=f"SELECT value NOT IN ({', '.join(literals)}) FROM output",
                dialect=dialect,
                schema={"output": {"value": column_type}},
            ),
        )
    )[0]


def _sql_test_columns(
    *, project: CompiledProject, profile: ExpressionInferenceProfile
) -> dict[str, tuple[str, ...]]:
    """Infer fixture interfaces in one batch instead of repeating Python AST walks."""
    bodies: dict[str, None] = {}
    for test in project.sql_tests:
        if isinstance(test.payload, CompiledModelSqlTestPayload):
            for cte in (*test.payload.authored_ctes, *test.payload.expected_ctes):
                bodies[cte.sql_body] = None
    queries: tuple[str, ...] = tuple(bodies)
    if not queries:
        return {}
    analyses: tuple[NativeQueryColumns, ...] = infer_native_query_columns(
        queries=tuple(
            NativeColumnQuery(sql=sql, mode="batch", recover_cte_facts=False) for sql in queries
        ),
        profile=profile,
    )
    result: dict[str, tuple[str, ...]] = {
        sql: tuple(column.name for column in analysis.columns or ())
        for sql, analysis in zip(queries, analyses, strict=True)
    }
    return result


def _names(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _model_error(
    *,
    model: CompiledModel,
    code: str,
    name: str,
    message: str,
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR,
) -> CompilerDiagnostic:
    line: int
    column: int
    line, column = _text_position(text=model.authored_sql, name=name)
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=severity,
        code=code,
        message=message,
        resource_type=CompiledResourceType.MODEL,
        resource_name=model.name,
        path=model.relative_path,
        line=line,
        column=column,
    )


def _text_position(*, text: str, name: str, offset: int = 0) -> tuple[int, int]:
    match: re.Match[str] | None = re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text[offset:])
    start: int = offset + match.start() if match else offset
    return text.count("\n", 0, start) + 1, start - text.rfind("\n", 0, start)
