"""Optional SQLGlot-backed output column inference from model query SQL."""

from __future__ import annotations

import re
from importlib import import_module
from typing import Any

from sqlbuild.compiler.compile.models import InferredColumn

_REF_PATTERN: re.Pattern[str] = re.compile(r'__ref\("([^"]+)"\)')
_SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')
_DBT_REF_PATTERN: re.Pattern[str] = re.compile(r'__dbt_ref\("([^"]+)"\)')


def infer_columns_with_sqlglot(*, query_sql: str) -> tuple[InferredColumn, ...] | None:
    """Infer output columns from model query SQL using SQLGlot.

    Returns None if SQLGlot is not available or the SQL cannot be parsed.
    Returns an empty tuple if the outermost SELECT uses SELECT * with no
    extractable column names.
    """

    try:
        sqlglot_module: Any = import_module("sqlglot")
        expressions_module: Any = import_module("sqlglot.expressions")
    except ModuleNotFoundError:
        return None

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)

    try:
        parsed: Any = sqlglot_module.parse_one(cleaned_sql)
    except Exception:
        return None

    select: Any | None = _find_outermost_select(
        parsed=parsed, expressions_module=expressions_module
    )
    if select is None:
        return None

    return _extract_columns_from_select(select=select, expressions_module=expressions_module)


def _replace_refs_with_stubs(query_sql: str) -> str:
    """Replace __ref/__source/__dbt_ref calls with plain table names for parsing."""

    result: str = _REF_PATTERN.sub(r"\1", query_sql)
    result = _SOURCE_PATTERN.sub(r"\1", result)
    result = _DBT_REF_PATTERN.sub(r"\1", result)
    return result


def _find_outermost_select(*, parsed: Any, expressions_module: Any) -> Any | None:
    """Find the outermost SELECT statement from a parsed expression."""

    union_type: type[Any] = expressions_module.Union
    select_type: type[Any] = expressions_module.Select
    intersect_type: type[Any] = expressions_module.Intersect
    except_type: type[Any] = expressions_module.Except

    if isinstance(parsed, (union_type, intersect_type, except_type)):
        return parsed.find(select_type)
    if isinstance(parsed, select_type):
        return parsed

    body: Any | None = getattr(parsed, "this", None)
    if body is None:
        return None
    if isinstance(body, (union_type, intersect_type, except_type)):
        return body.find(select_type)
    if isinstance(body, select_type):
        return body
    return parsed.find(select_type)


def _extract_columns_from_select(
    *, select: Any, expressions_module: Any
) -> tuple[InferredColumn, ...]:
    """Extract output column names and types from a SELECT's projection list."""

    star_type: type[Any] = expressions_module.Star
    alias_type: type[Any] = expressions_module.Alias
    column_type: type[Any] = expressions_module.Column
    cast_type: type[Any] = expressions_module.Cast
    try_cast_type: type[Any] = expressions_module.TryCast

    projection_list: list[Any] = select.args.get("expressions", [])
    columns: list[InferredColumn] = []

    expression: Any
    for expression in projection_list:
        if isinstance(expression, star_type):
            continue

        name: str
        inner: Any
        if isinstance(expression, alias_type):
            name = expression.alias
            inner = expression.this
        elif isinstance(expression, column_type):
            name = expression.name
            inner = expression
        else:
            continue

        col_type: str | None = None
        if isinstance(inner, (cast_type, try_cast_type)):
            col_type = inner.to.sql()

        columns.append(InferredColumn(name=name, type=col_type))

    return tuple(columns)
