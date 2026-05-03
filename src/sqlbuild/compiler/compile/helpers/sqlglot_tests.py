"""Optional SQLGlot-backed SQL-native test helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError


def extract_expected_branch_column_names_with_sqlglot(
    *, sql: str, file_label: str
) -> tuple[tuple[str, ...], ...] | None:
    """Return expected SELECT branch names using SQLGlot when it is installed."""

    try:
        sqlglot_module: Any = import_module("sqlglot")
        expressions_module: Any = import_module("sqlglot.expressions")
    except ModuleNotFoundError:
        return None

    try:
        parsed_expression: Any = sqlglot_module.parse_one(sql)
    except Exception:
        return None
    return _extract_branch_names(
        expression=parsed_expression,
        expressions_module=expressions_module,
        file_label=file_label,
    )


def _extract_branch_names(
    *, expression: Any, expressions_module: Any, file_label: str
) -> tuple[tuple[str, ...], ...]:
    expression = _unwrap_expression(expression=expression)
    union_type: type[Any] = expressions_module.Union
    select_type: type[Any] = expressions_module.Select
    if isinstance(expression, union_type):
        left_expression: Any = expression.args["this"]
        right_expression: Any = expression.args["expression"]
        return (
            *_extract_branch_names(
                expression=left_expression,
                expressions_module=expressions_module,
                file_label=file_label,
            ),
            *_extract_branch_names(
                expression=right_expression,
                expressions_module=expressions_module,
                file_label=file_label,
            ),
        )
    if isinstance(expression, select_type):
        return (
            _extract_select_names(
                expression=expression, expressions_module=expressions_module, file_label=file_label
            ),
        )
    raise CompileInputError(
        f"SQL test '{file_label}' must define each __expected__<model> set-operation "
        "branch as a SELECT query"
    )


def _unwrap_expression(*, expression: Any) -> Any:
    while expression.__class__.__name__ in {"Subquery", "Paren"}:
        expression = expression.this
    return expression


def _extract_select_names(
    *, expression: Any, expressions_module: Any, file_label: str
) -> tuple[str, ...]:
    names: list[str] = []
    projection: Any
    for projection in expression.expressions:
        if isinstance(projection, expressions_module.Star):
            raise CompileInputError(
                f"SQL test '{file_label}' must not use SELECT * in __expected__<model> CTEs"
            )
        alias_name: str = projection.alias
        if alias_name:
            names.append(alias_name)
            continue
        if isinstance(projection, expressions_module.Column):
            names.append(projection.name)
            continue
        raise CompileInputError(
            f"SQL test '{file_label}' must alias every non-trivial __expected__<model> projection"
        )
    if not names:
        raise CompileInputError(
            f"SQL test '{file_label}' must project at least one column in __expected__<model>"
        )
    return tuple(names)
