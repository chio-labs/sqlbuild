"""Check column-bearing model metadata against authoritative output shapes."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, cast

from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.contract.types import TypeFamily
from sqlbuild.adapter.type_system.main.normalize_type import normalize_type
from sqlbuild.compiler.compile._helpers.analysis.columns import _polyglot_expression_type
from sqlbuild.compiler.compile._helpers.analysis.compact import (
    analyze_columns_and_lineage_with_polyglot,
    get_complete_schema_binding_request,
)
from sqlbuild.compiler.compile._helpers.assembly.semantic_shapes import semantic_shapes
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompilerDiagnostic,
    PolyglotAnalysisResult,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.compiler.sql_analysis.constants import BINDING_UNKNOWN_TABLE_INTERNAL_CODE
from sqlbuild.compiler.sql_analysis.main._schema_validation import get_schema_validations
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql
from sqlbuild.compiler.sql_analysis.models import SqlBindingResult, SqlSchemaValidationRequest
from sqlbuild.spec.contracts.models import SchemaAuditInstance

_UNKNOWN_TYPE: str = "UNKNOWN"
_EXPRESSION_AUDIT: str = "expression_is_true"
_RELATIONSHIPS_AUDIT: str = "relationships"
_ACCEPTED_VALUES_AUDIT: str = "accepted_values"
_SELECT_KIND: str = "select"
_FUNCTION_KIND: str = "function"
_CURSOR_FAMILIES: dict[str, frozenset[TypeFamily]] = {
    "integer": frozenset({TypeFamily.INTEGER, TypeFamily.DECIMAL}),
    "timestamp": frozenset({TypeFamily.TIMESTAMP, TypeFamily.DATETIME}),
    "date": frozenset({TypeFamily.DATE}),
}


def get_semantic_metadata_diagnostics(
    *,
    project: CompiledProject,
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    """Reject metadata names only where absence can be proven."""

    if not project.settings.sql_analysis:
        return ()
    shapes: dict[str, dict[str, str]] = semantic_shapes(project=project, profile=profile)
    diagnostics: list[CompilerDiagnostic] = []
    for model in project.models:
        if model.config.values.get("sql_analysis") is False or not model.binding_validated:
            continue
        diagnostics.extend(
            _function_errors(model=model, project=project, shapes=shapes, profile=profile)
        )
        shape: dict[str, str] | None = shapes.get(model.name)
        if shape is None:
            continue
        diagnostics.extend(_audit_errors(model=model, shape=shape, shapes=shapes, profile=profile))
        values: dict[str, object] = model.config.values
        references: list[tuple[str, str, dict[str, str]]] = []
        for key in ("unique_key", "cursor", "partition_column", "row_diff_exclude_columns"):
            references.extend((key, name, shape) for name in _names(values.get(key)))
        custom: object = values.get("config")
        if isinstance(custom, dict):
            references.extend(
                ("partition_column", name, shape)
                for name in _names(cast(dict[str, object], custom).get("partition_column"))
            )
        tolerances: object = values.get("row_diff_tolerances")
        by_column: object = (
            cast(dict[str, object], tolerances).get("by_column")
            if isinstance(tolerances, dict)
            else None
        )
        if isinstance(by_column, dict):
            references.extend(("row_diff_tolerances", str(name), shape) for name in by_column)
        cursor_inputs: object = values.get("cursor_inputs")
        if isinstance(cursor_inputs, dict):
            for upstream, columns in cursor_inputs.items():
                upstream_shape: dict[str, str] | None = shapes.get(str(upstream))
                if upstream_shape is not None:
                    references.extend(
                        (f"cursor_inputs {upstream}", name, upstream_shape)
                        for name in _names(columns)
                    )
        for key, name, reference_shape in references:
            if name.casefold() not in {column.casefold() for column in reference_shape}:
                diagnostics.append(
                    _model_error(
                        model=model,
                        code="B300",
                        name=name,
                        message=f"{key} references unknown column '{name}'",
                    )
                )
        cursor: object = values.get("cursor")
        cursor_type: object = values.get("cursor_type")
        if isinstance(cursor, str) and isinstance(cursor_type, str):
            actual: str = next(
                (value for key, value in shape.items() if key.casefold() == cursor.casefold()),
                "UNKNOWN",
            )
            if cursor_type.lower() in _CURSOR_FAMILIES:
                family: TypeFamily = normalize_type(
                    type_sql=actual, dialect=profile.sql_analysis_dialect
                ).family
                if (
                    family != TypeFamily.OTHER
                    and family not in _CURSOR_FAMILIES[cursor_type.lower()]
                ):
                    diagnostics.append(
                        _model_error(
                            model=model,
                            code="B301",
                            name=cursor,
                            message=(
                                f"cursor_type {cursor_type} does not match "
                                f"column '{cursor}' type {actual}"
                            ),
                        )
                    )
    for source in project.sources:
        cursor = source.source_entry.cursor_column
        shape = shapes.get(source.name)
        if (
            cursor
            and shape is not None
            and cursor.casefold() not in {name.casefold() for name in shape}
        ):
            line: int
            column: int
            line, column = _text_position(text=source.source_file.contents, name=cursor)
            diagnostics.append(
                CompilerDiagnostic(
                    phase=DiagnosticPhase.COMPILE,
                    severity=DiagnosticSeverity.ERROR,
                    code="B300",
                    message=f"cursor_column references unknown column '{cursor}'",
                    resource_type=CompiledResourceType.SOURCE,
                    resource_name=source.name,
                    path=source.source_file.relative_path,
                    line=line,
                    column=column,
                )
            )
    diagnostics.extend(_sql_test_errors(project=project, shapes=shapes, profile=profile))
    return tuple(diagnostics)


def _audit_errors(
    *,
    model: CompiledModel,
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
                        ),
                    )
                )[0]
                diagnostics.extend(
                    _model_error(
                        model=model,
                        code=diagnostic.code,
                        name=expression,
                        message=f"expression_is_true: {diagnostic.message}",
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
            if target_shape is not None and field not in target_shape:
                diagnostics.append(
                    _model_error(
                        model=model,
                        code="B300",
                        name=field,
                        message=f"relationships target has no column '{field}'",
                    )
                )
            elif (
                target_shape is not None
                and column in shape
                and _incompatible(left=shape[column], right=target_shape[field], profile=profile)
            ):
                diagnostics.append(
                    _model_error(
                        model=model,
                        code="B301",
                        name=column,
                        message=(
                            f"relationships column '{column}' type {shape[column]} "
                            f"is incompatible with '{field}' type {target_shape[field]}"
                        ),
                    )
                )
        elif audit.definition_name == _ACCEPTED_VALUES_AUDIT and column in shape:
            values: object = arguments.get("values")
            if isinstance(values, (list, tuple)):
                for value in values:
                    value_type: str = (
                        "BOOLEAN"
                        if isinstance(value, bool)
                        else "INTEGER"
                        if isinstance(value, int)
                        else "DOUBLE"
                        if isinstance(value, float)
                        else "VARCHAR"
                        if isinstance(value, str)
                        else "UNKNOWN"
                    )
                    if _incompatible(left=shape[column], right=value_type, profile=profile):
                        diagnostics.append(
                            _model_error(
                                model=model,
                                code="B301",
                                name=column,
                                message=(
                                    f"accepted_values value {value!r} is incompatible "
                                    f"with column '{column}' type {shape[column]}"
                                ),
                            )
                        )
                        break
    return tuple(diagnostics)


def _incompatible(*, left: str, right: str, profile: ExpressionInferenceProfile) -> bool:
    families: set[TypeFamily] = {
        normalize_type(type_sql=value, dialect=profile.sql_analysis_dialect).family
        for value in (left, right)
    }
    return (
        len(families) > 1
        and TypeFamily.OTHER not in families
        and not families <= {TypeFamily.INTEGER, TypeFamily.DECIMAL, TypeFamily.FLOAT}
        and not families <= {TypeFamily.TIMESTAMP, TypeFamily.DATE, TypeFamily.DATETIME}
    )


def _sql_test_errors(
    *,
    project: CompiledProject,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    diagnostics: list[CompilerDiagnostic] = []
    for test in project.sql_tests:
        if not isinstance(test.payload, CompiledModelSqlTestPayload):
            continue
        for cte in (*test.payload.authored_ctes, *test.payload.expected_ctes):
            match: re.Match[str] | None = re.match(
                r"__(?:expected|ref|source|seed)__(.+)$", cte.name
            )
            shape: dict[str, str] | None = shapes.get(match.group(1)) if match else None
            if shape is None:
                continue
            analysis: PolyglotAnalysisResult = analyze_columns_and_lineage_with_polyglot(
                query_sql=cte.sql_body,
                references=(),
                inference_profile=profile,
                allow_compact_analysis=True,
            )
            for column in analysis.columns or ():
                if column.name.casefold() not in {name.casefold() for name in shape}:
                    line: int
                    column_position: int
                    line, column_position = _text_position(
                        text=test.test_file.contents,
                        name=column.name,
                        offset=max(test.test_file.contents.find(cte.name), 0),
                    )
                    diagnostics.append(
                        CompilerDiagnostic(
                            phase=DiagnosticPhase.COMPILE,
                            severity=DiagnosticSeverity.ERROR,
                            code="B302",
                            message=f"SQL test '{cte.name}' names unknown column '{column.name}'",
                            resource_type=CompiledResourceType.SQL_TEST,
                            resource_name=test.name,
                            path=test.test_file.relative_path,
                            line=line,
                            column=column_position,
                        )
                    )
    return tuple(diagnostics)


def _names(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (tuple, list)):
        return tuple(item for item in value if isinstance(item, str))
    return ()


def _function_errors(
    *,
    model: CompiledModel,
    project: CompiledProject,
    shapes: dict[str, dict[str, str]],
    profile: ExpressionInferenceProfile,
) -> tuple[CompilerDiagnostic, ...]:
    functions: dict[str, CompiledFunction] = {
        function.name.casefold(): function for function in project.functions
    }
    if not functions or not any(
        reference.ref_kind in {SqlReferenceKind.UDF, SqlReferenceKind.TABLE_FUNCTION}
        for reference in model.references
    ):
        return ()
    module: Any = import_polyglot_sql()
    request: SqlSchemaValidationRequest = get_complete_schema_binding_request(
        query_sql=model.query_sql,
        placeholders=None,
        dialect=profile.sql_analysis_dialect,
        binding_schema=shapes,
    )
    try:
        parsed: Any = module.parse_one(request.sql, dialect=profile.sql_analysis_dialect)
    except module.PolyglotError:
        return ()
    diagnostics: list[CompilerDiagnostic] = []
    for call, select in _function_scopes(parsed):
        payload: dict[str, Any] = call.to_dict().get("function", {})
        name: str = str(payload.get("name", "")).removeprefix("__sqlbuild_udf_")
        function: CompiledFunction | None = functions.get(name.casefold())
        if function is None:
            continue
        arguments: list[dict[str, Any]] = payload.get("args", [])
        if len(arguments) != len(function.arguments):
            diagnostics.append(
                _model_error(
                    model=model,
                    code="B102",
                    name=name,
                    message=(
                        f"Function '{name}' expects {len(function.arguments)} arguments "
                        f"but received {len(arguments)}"
                    ),
                )
            )
            continue
        argument_expressions: list[Any] = call.expressions
        for argument, expression, declaration in zip(
            arguments, argument_expressions, function.arguments, strict=True
        ):
            actual: str = (
                _polyglot_expression_type(expression=expression, inference_profile=profile)
                or _UNKNOWN_TYPE
            )
            literal: Any = argument.get("literal")
            column: Any = argument.get("column")
            if literal:
                actual = {"string": "VARCHAR", "number": "DOUBLE", "boolean": "BOOLEAN"}.get(
                    literal.get("literal_type"), "UNKNOWN"
                )
            elif column:
                actual = _argument_column_type(column=column, select=select, shapes=shapes)
            if actual != _UNKNOWN_TYPE and _incompatible(
                left=actual, right=declaration.type, profile=profile
            ):
                diagnostics.append(
                    _model_error(
                        model=model,
                        code="B301",
                        name=name,
                        message=(
                            f"Function '{name}' argument '{declaration.name}' "
                            f"expects {declaration.type}, received {actual}"
                        ),
                    )
                )
    return tuple(diagnostics)


def _function_scopes(root: Any) -> Iterator[tuple[Any, Any]]:
    pending: list[tuple[Any, Any]] = [(root, None)]
    node: Any
    select: Any
    while pending:
        node, select = pending.pop()
        if node.kind == _SELECT_KIND:
            select = node
        if node.kind == _FUNCTION_KIND:
            yield node, select
        pending.extend((child, select) for child in reversed(node.children()))


def _argument_column_type(
    *, column: dict[str, Any], select: Any, shapes: dict[str, dict[str, str]]
) -> str:
    if select is None:
        return _UNKNOWN_TYPE
    payload: dict[str, Any] = select.to_dict().get("select", {})
    relations: list[dict[str, Any]] = list((payload.get("from") or {}).get("expressions", []))
    relations.extend(join.get("this", {}) for join in payload.get("joins", []))
    qualifier: str | None = (column.get("table") or {}).get("name")
    name: str = str(column.get("name", {}).get("name", ""))
    candidates: list[str] = []
    for relation in relations:
        table: dict[str, Any] = relation.get("table", {})
        table_name: str = str(table.get("name", {}).get("name", ""))
        alias: str = str((table.get("alias") or {}).get("name", table_name))
        if qualifier is not None and qualifier.casefold() != alias.casefold():
            continue
        shape: dict[str, str] | None = shapes.get(table_name)
        if shape is None:
            return _UNKNOWN_TYPE
        candidates.extend(
            value for key, value in shape.items() if key.casefold() == name.casefold()
        )
    return candidates[0] if len(candidates) == 1 else _UNKNOWN_TYPE


def _model_error(*, model: CompiledModel, code: str, name: str, message: str) -> CompilerDiagnostic:
    line: int
    column: int
    line, column = _text_position(text=model.authored_sql, name=name)
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
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
