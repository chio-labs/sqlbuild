"""Recognition and rendering for model cursor-bound SQL intrinsics."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.compiler.compile.constants import (
    SQL_OPEN_PAREN_TOKEN,
    SQL_QUOTE_TOKENS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.planner.constants import (
    MICROBATCH_END_SENTINEL,
    MICROBATCH_START_SENTINEL,
)
from sqlbuild.compiler.planner.types import CursorType, MaterializationType
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text

_CURSOR_START_INTRINSIC: str = "__cursor_start"
_CURSOR_END_INTRINSIC: str = "__cursor_end"
_INTRINSIC_NAMES: tuple[str, ...] = (_CURSOR_START_INTRINSIC, _CURSOR_END_INTRINSIC)
_IDENTIFIER_JOIN_CHARACTER: str = "_"


def get_validated_model_cursor_intrinsics(
    *, sql: str, config_values: dict[str, object], model_name: str
) -> str:
    """Validate and canonicalize intrinsics in one model query."""

    _assert_no_reserved_cursor_markers(sql=sql, context=f"Model '{model_name}'")
    canonical_sql, found = _transform_cursor_intrinsics(
        sql=sql,
        replacement=lambda name: f"{name}()",
        context=f"Model '{model_name}'",
    )
    if not found:
        return canonical_sql
    if config_values.get("materialized") != MaterializationType.INCREMENTAL:
        raise CompileInputError(
            f"Model '{model_name}' uses cursor intrinsics but is not a built-in incremental model"
        )
    cursor: object | None = config_values.get("cursor")
    if not isinstance(cursor, str) or not cursor.strip():
        raise CompileInputError(
            f"Model '{model_name}' uses cursor intrinsics but does not declare a cursor"
        )
    return canonical_sql


def reject_cursor_intrinsics(*, sql: str, context: str) -> None:
    """Reject cursor intrinsics in SQL that does not own an execution interval."""

    _assert_no_reserved_cursor_markers(sql=sql, context=context)
    _, found = _transform_cursor_intrinsics(
        sql=sql,
        replacement=lambda name: f"{name}()",
        context=context,
    )
    if found:
        raise CompileInputError(
            f"{context} uses cursor intrinsics, which are only supported in cursor-based "
            "incremental model query SQL"
        )


def render_cursor_intrinsics(*, sql: str, start_sql: str, end_sql: str) -> str:
    """Render recognized intrinsics to complete adapter-specific bound expressions."""

    rendered, _ = _transform_cursor_intrinsics(
        sql=sql,
        replacement=lambda name: start_sql if name == _CURSOR_START_INTRINSIC else end_sql,
        context="Model SQL",
    )
    return rendered


def cursor_intrinsics_analysis_sql(*, sql: str, cursor_type: object) -> str:
    """Replace intrinsics with stable typed literals only for static SQL analysis."""

    literal: str = (
        "CAST(0 AS BIGINT)"
        if cursor_type == CursorType.INTEGER
        else "CAST('2000-01-01 00:00:00' AS TIMESTAMP)"
    )
    return render_cursor_intrinsics(sql=sql, start_sql=literal, end_sql=literal)


def has_cursor_intrinsics(sql: str) -> bool:
    """Return whether executable SQL contains either cursor intrinsic."""

    _, found = _transform_cursor_intrinsics(
        sql=sql,
        replacement=lambda name: f"{name}()",
        context="SQL",
    )
    return found


def _transform_cursor_intrinsics(
    *, sql: str, replacement: Callable[[str], str], context: str
) -> tuple[str, bool]:
    if not any(name in sql for name in _INTRINSIC_NAMES):
        return sql, False

    parts: list[str] = []
    last_index: int = 0
    index: int = 0
    found: bool = False
    while index < len(sql):
        character: str = sql[index]
        if character in SQL_QUOTE_TOKENS:
            index = skip_quoted_text(sql=sql, start=index, context=context)
            continue
        if sql.startswith("--", index):
            index = skip_line_comment(sql=sql, start=index)
            continue
        if sql.startswith("/*", index):
            index = skip_block_comment(sql=sql, start=index, context=context)
            continue

        name: str | None = next(
            (
                candidate
                for candidate in _INTRINSIC_NAMES
                if sql.startswith(candidate, index)
                and _is_identifier_boundary(sql=sql, start=index, end=index + len(candidate))
            ),
            None,
        )
        if name is None:
            index += 1
            continue

        call_start: int = _skip_whitespace(sql=sql, start=index + len(name))
        if call_start >= len(sql) or sql[call_start] != SQL_OPEN_PAREN_TOKEN:
            raise CompileInputError(f"{context} intrinsic {name} must be called with ()")
        call_end: int = find_matching_paren(
            sql=sql,
            open_paren_index=call_start,
            context=f"{context} cursor intrinsic",
        )
        if sql[call_start + 1 : call_end].strip():
            raise CompileInputError(f"{context} intrinsic {name} does not accept arguments")
        parts.append(sql[last_index:index])
        parts.append(replacement(name))
        last_index = call_end + 1
        index = call_end + 1
        found = True

    parts.append(sql[last_index:])
    return "".join(parts), found


def _assert_no_reserved_cursor_markers(*, sql: str, context: str) -> None:
    if MICROBATCH_START_SENTINEL in sql or MICROBATCH_END_SENTINEL in sql:
        raise CompileInputError(f"{context} contains a reserved internal cursor marker")


def _skip_whitespace(*, sql: str, start: int) -> int:
    index: int = start
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index


def _is_identifier_boundary(*, sql: str, start: int, end: int) -> bool:
    before: str | None = sql[start - 1] if start > 0 else None
    after: str | None = sql[end] if end < len(sql) else None
    return not _is_identifier_character(before) and not _is_identifier_character(after)


def _is_identifier_character(character: str | None) -> bool:
    return character is not None and (
        character.isalnum() or character == _IDENTIFIER_JOIN_CHARACTER
    )
