"""Native semantic metadata checks, with Python's audit and resource SQL checks in order."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.adapter.contract.models import ExpressionInferenceProfile
from sqlbuild.adapter.type_system.main.normalize_type import normalize_type
from sqlbuild.compiler.compile.classes.semantic_completion_inputs import SemanticCompletionInputs
from sqlbuild.compiler.compile.models import (
    CompiledFunction,
    CompiledModel,
    CompiledModelSqlTestPayload,
    CompiledProject,
    CompiledSource,
    CompiledSqlTest,
    CompilerDiagnostic,
)
from sqlbuild.compiler.compile.types import (
    CompiledResourceType,
    DiagnosticPhase,
    DiagnosticSeverity,
)
from sqlbuild.compiler.discovery.constants import SQL_ANALYSIS_CONFIG_KEY
from sqlbuild.compiler.semantic_checks.constants import (
    METADATA_CONFIG_KEYS,
    METADATA_FUNCTION_REFERENCE_KINDS,
)
from sqlbuild.spec.contracts.models import SourceLocation

type _ErrorRow = tuple[str, str, int, int]
type _NamesRow = tuple[str, list[str]]


def native_metadata_diagnostics(
    *,
    project: CompiledProject,
    profile: ExpressionInferenceProfile,
    resource_sql_analysis: bool,
    catalog: object,
) -> tuple[CompilerDiagnostic, ...]:
    """The project's semantic metadata diagnostics; a native internal failure raises."""

    if not project.settings.sql_analysis:
        return ()
    shapes: dict[str, dict[str, str]] = SemanticCompletionInputs.metadata_shapes(
        project=project, profile=profile
    )
    tests: list[CompiledSqlTest] = [
        test for test in project.sql_tests if isinstance(test.payload, CompiledModelSqlTestPayload)
    ]
    columns_by_sql: dict[str, tuple[str, ...]] = SemanticCompletionInputs.sql_test_columns(
        project=project, profile=profile
    )
    functions: dict[str, CompiledFunction] = {
        function.name.casefold(): function for function in project.functions
    }
    file_texts: dict[Path, str] = {}
    for source in project.sources:
        _ = file_texts.setdefault(source.source_file.file_path, source.source_file.contents)
    for test in tests:
        _ = file_texts.setdefault(test.test_file.file_path, test.test_file.contents)
    files: dict[Path, int] = {path: index for index, path in enumerate(file_texts)}
    request: Any = (
        profile.sql_analysis_dialect,
        list(profile.function_return_types.items()),
        [_function_payload(key=key, function=function) for key, function in functions.items()],
        [(name, list(columns.items())) for name, columns in shapes.items()],
        [_model_payload(model) for model in project.models],
        list(file_texts.values()),
        [_source_payload(source=source, files=files) for source in project.sources],
        [
            _sql_test_payload(test=test, columns_by_sql=columns_by_sql, files=files)
            for test in tests
        ],
    )
    model_rows, source_rows, test_rows, fallback_types = _native.check_semantic_metadata_rows(
        catalog, request
    )
    for type_sql in fallback_types:
        _ = normalize_type(type_sql=type_sql, dialect=profile.sql_analysis_dialect)
    diagnostics: list[CompilerDiagnostic] = []
    for model, (function_rows, reference_rows) in zip(project.models, model_rows, strict=True):
        if not _checked(model):
            continue
        diagnostics.extend(_model_error(model=model, row=row) for row in function_rows)
        shape: dict[str, str] | None = shapes.get(model.name)
        if shape is None:
            continue
        diagnostics.extend(
            SemanticCompletionInputs.audit_diagnostics(
                model=model, project=project, shape=shape, shapes=shapes, profile=profile
            )
        )
        diagnostics.extend(_model_error(model=model, row=row) for row in reference_rows)
    diagnostics.extend(
        _source_error(source=project.sources[index], row=row) for index, row in source_rows
    )
    diagnostics.extend(
        _sql_test_error(test=tests[index], row=row, end_column=end_column)
        for index, row, end_column in test_rows
    )
    if resource_sql_analysis:
        diagnostics.extend(
            SemanticCompletionInputs.resource_sql_diagnostics(
                project=project, shapes=shapes, profile=profile
            )
        )
    return tuple(diagnostics)


def _function_payload(*, key: str, function: CompiledFunction) -> tuple[str, list[tuple[str, str]]]:
    return (key, [(argument.name, argument.type) for argument in function.arguments])


def _checked(model: CompiledModel) -> bool:
    return model.config.values.get(SQL_ANALYSIS_CONFIG_KEY) is not False and model.binding_validated


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _model_payload(model: CompiledModel) -> tuple[Any, ...]:
    values: dict[str, object] = model.config.values
    references: list[_NamesRow] = [
        (key, list(SemanticCompletionInputs.column_names(values.get(key))))
        for key in METADATA_CONFIG_KEYS
    ]
    custom: object = values.get("config")
    if isinstance(custom, dict):
        partition: object = cast(dict[str, object], custom).get("partition_column")
        references.append(
            ("partition_column", list(SemanticCompletionInputs.column_names(partition)))
        )
    tolerances: object = values.get("row_diff_tolerances")
    by_column: object = (
        cast(dict[str, object], tolerances).get("by_column")
        if isinstance(tolerances, dict)
        else None
    )
    if isinstance(by_column, dict):
        references.append(("row_diff_tolerances", [str(name) for name in by_column]))
    cursor_inputs: object = values.get("cursor_inputs")
    upstreams: list[_NamesRow] = []
    if isinstance(cursor_inputs, dict):
        upstreams = [
            (str(upstream), list(SemanticCompletionInputs.column_names(columns)))
            for upstream, columns in cursor_inputs.items()
        ]
    return (
        model.name,
        model.query_sql,
        model.authored_sql,
        _checked(model),
        any(
            reference.ref_kind in METADATA_FUNCTION_REFERENCE_KINDS
            for reference in model.references
        ),
        references,
        upstreams,
        _string(values.get("cursor")),
        _string(values.get("cursor_type")),
    )


def _source_payload(
    *, source: CompiledSource, files: dict[Path, int]
) -> tuple[str, str | None, int]:
    return (
        source.name,
        source.source_entry.cursor_column or None,
        files[source.source_file.file_path],
    )


def _sql_test_payload(
    *, test: CompiledSqlTest, columns_by_sql: dict[str, tuple[str, ...]], files: dict[Path, int]
) -> tuple[int, list[_NamesRow]]:
    payload: CompiledModelSqlTestPayload = cast(CompiledModelSqlTestPayload, test.payload)
    return (
        files[test.test_file.file_path],
        [
            (cte.name, list(columns_by_sql[cte.sql_body]))
            for cte in (*payload.authored_ctes, *payload.expected_ctes)
        ],
    )


def _model_error(*, model: CompiledModel, row: _ErrorRow) -> CompilerDiagnostic:
    code, message, line, column = row
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


def _source_error(*, source: CompiledSource, row: _ErrorRow) -> CompilerDiagnostic:
    code, message, line, column = row
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=code,
        message=message,
        resource_type=CompiledResourceType.SOURCE,
        resource_name=source.name,
        path=source.source_file.relative_path,
        line=line,
        column=column,
    )


def _sql_test_error(
    *, test: CompiledSqlTest, row: _ErrorRow, end_column: int
) -> CompilerDiagnostic:
    code, message, line, column = row
    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.ERROR,
        code=code,
        message=message,
        resource_type=CompiledResourceType.SQL_TEST,
        resource_name=test.name,
        path=test.test_file.relative_path,
        line=line,
        column=column,
        location=SourceLocation(
            path=test.test_file.relative_path,
            line=line,
            column=column,
            end_line=line,
            end_column=end_column,
        ),
    )
