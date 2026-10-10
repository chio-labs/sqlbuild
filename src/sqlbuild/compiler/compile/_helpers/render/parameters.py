"""Typed parameter expansion for SQL-native test cases."""

from __future__ import annotations

import re
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.sql_values.exceptions import SqlValueRenderingError, SqlValueValidationError
from sqlbuild.sql_values.main.validate_rendered_size import validate_rendered_sql_value_size
from sqlbuild.sql_values.models import SqlValue

_PARAMETER_REFERENCE: re.Pattern[str] = re.compile(
    r'@param(?![A-Za-z0-9_])\s*\(\s*"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"\s*\)'
)
_PARAMETER_TOKEN: re.Pattern[str] = re.compile(r"@param(?![A-Za-z0-9_])")


def expand_test_parameters(
    *,
    sql: str,
    file_path: Path,
    values: tuple[tuple[str, SqlValue], ...],
    value_renderer: TypedSqlValueRenderer,
    test_name: str,
    case_name: str,
) -> tuple[str, frozenset[str]]:
    """Render active parameter references while leaving comments and quoted text unchanged."""

    value_lookup: dict[str, SqlValue] = dict(values)
    references, error = _native.scan_test_parameter_references(
        sql, list(value_lookup), f"SQL test '{test_name}' case '{case_name}' in '{file_path}'"
    )
    expanded: tuple[str, frozenset[str]] = _splice_parameter_references(
        sql=sql,
        references=references,
        value_lookup=value_lookup,
        value_renderer=value_renderer,
        test_name=test_name,
        case_name=case_name,
    )
    if error is not None:
        raise CompileInputError(error)
    return expanded


def _splice_parameter_references(
    *,
    sql: str,
    references: list[tuple[int, int, str]],
    value_lookup: dict[str, SqlValue],
    value_renderer: TypedSqlValueRenderer,
    test_name: str,
    case_name: str,
) -> tuple[str, frozenset[str]]:
    parts: list[str] = []
    cursor: int = 0
    for start, end, name in references:
        parts.append(sql[cursor:start])
        parts.append(
            _render_parameter(
                name=name,
                value=value_lookup[name],
                value_renderer=value_renderer,
                test_name=test_name,
                case_name=case_name,
            )
        )
        cursor = end
    parts.append(sql[cursor:])
    return "".join(parts), frozenset(name for _start, _end, name in references)


def _render_parameter(
    *,
    name: str,
    value: SqlValue,
    value_renderer: TypedSqlValueRenderer,
    test_name: str,
    case_name: str,
) -> str:
    try:
        rendered: str = value_renderer.render_typed_scalar(value=value)
        validate_rendered_sql_value_size(
            rendered_sql=rendered,
            context=(f"SQL test '{test_name}' case '{case_name}' parameter '{name}'"),
        )
    except (SqlValueRenderingError, SqlValueValidationError) as error:
        raise CompileInputError(
            f"SQL test '{test_name}' case '{case_name}' parameter '{name}' could not "
            f"be rendered by adapter '{value_renderer.adapter_name}': {error}"
        ) from error
    return rendered
