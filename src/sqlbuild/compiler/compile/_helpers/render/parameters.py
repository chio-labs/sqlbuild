"""Typed parameter expansion for SQL-native test cases."""

from __future__ import annotations

import re
from pathlib import Path

from sqlbuild.compiler.compile.constants import SQL_QUOTE_TOKENS
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.types import TypedSqlValueRenderer
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text
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
    used_names: set[str] = set()
    parts: list[str] = []
    cursor: int = 0
    while cursor < len(sql):
        character: str = sql[cursor]
        if character in SQL_QUOTE_TOKENS:
            end: int = skip_quoted_text(sql=sql, start=cursor)
            parts.append(sql[cursor:end])
            cursor = end
            continue
        if sql.startswith("--", cursor):
            end = skip_line_comment(sql=sql, start=cursor)
            parts.append(sql[cursor:end])
            cursor = end
            continue
        if sql.startswith("/*", cursor):
            end = skip_block_comment(sql=sql, start=cursor)
            parts.append(sql[cursor:end])
            cursor = end
            continue
        if _PARAMETER_TOKEN.match(sql, cursor):
            match: re.Match[str] | None = _PARAMETER_REFERENCE.match(sql, cursor)
            if match is None:
                raise CompileInputError(
                    f"SQL test '{test_name}' case '{case_name}' in '{file_path}' has malformed "
                    "@param reference; expected "
                    '@param("name")'
                )
            name: str = match.group("name")
            value: SqlValue | None = value_lookup.get(name)
            if value is None:
                raise CompileInputError(
                    f"SQL test '{test_name}' case '{case_name}' in '{file_path}' references "
                    f"undeclared parameter '{name}'"
                )
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
            parts.append(rendered)
            used_names.add(name)
            cursor = match.end()
            continue
        parts.append(character)
        cursor += 1
    return "".join(parts), frozenset(used_names)
