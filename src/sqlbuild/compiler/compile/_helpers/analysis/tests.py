"""Optional Polyglot-backed SQL-native test helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.constants import (
    POLYGLOT_COLUMN_EXPRESSION_NAME,
    POLYGLOT_SELECT_EXPRESSION_NAME,
    POLYGLOT_SET_OPERATION_EXPRESSION_NAMES,
    POLYGLOT_WRAPPER_EXPRESSION_NAMES,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.sql_analysis.main._split_set_operation_branches import (
    split_set_operation_branches,
)
from sqlbuild.compiler.sql_analysis.main.import_polyglot_sql import import_polyglot_sql

_POLYGLOT_VALUES_EXPRESSION_NAME: str = "Values"
_POLYGLOT_VALUES_SET_ALIAS: str = "_values"
_SCAN_CONTEXT: str = "SQL test"


def extract_expected_branch_column_names_with_sql_analysis(
    *, sql: str, file_label: str, label: str = "__expected__<model>"
) -> tuple[tuple[str, ...], ...] | None:
    """Return expected SELECT branch names using required Polyglot analysis."""

    polyglot_module: Any = import_polyglot_sql()

    try:
        parsed_expression: Any = polyglot_module.parse_one(sql, dialect="generic")
    except polyglot_module.PolyglotError:
        return _extract_unparsed_branch_names(
            sql=sql, polyglot_module=polyglot_module, file_label=file_label, label=label
        )
    return _extract_branch_names(expression=parsed_expression, file_label=file_label, label=label)


def _extract_unparsed_branch_names(
    *, sql: str, polyglot_module: Any, file_label: str, label: str
) -> tuple[tuple[str, ...], ...] | None:
    """Parse each top-level set-operation branch separately when the whole query cannot parse."""

    branches: tuple[str, ...] = split_set_operation_branches(sql=sql, context=_SCAN_CONTEXT)
    if len(branches) <= 1:
        return None
    try:
        parsed_branches: tuple[Any, ...] = tuple(
            polyglot_module.parse_one(branch_sql, dialect="generic") for branch_sql in branches
        )
    except polyglot_module.PolyglotError:
        return None
    return tuple(
        _extract_branch_names(expression=expression, file_label=file_label, label=label)[0]
        for expression in parsed_branches
    )


def _extract_branch_names(
    *, expression: Any, file_label: str, label: str
) -> tuple[tuple[str, ...], ...]:
    expression = _unwrap_expression(expression=expression)
    if expression.__class__.__name__ in POLYGLOT_SET_OPERATION_EXPRESSION_NAMES:
        left_expression: Any = expression.args["left"]
        right_expression: Any = expression.args["right"]
        return (
            *_extract_branch_names(expression=left_expression, file_label=file_label, label=label),
            *_extract_branch_names(expression=right_expression, file_label=file_label, label=label),
        )
    if expression.__class__.__name__ == POLYGLOT_SELECT_EXPRESSION_NAME:
        if _is_synthetic_values_set_branch(expression):
            raise CompileInputError(
                f"SQL test '{file_label}' must define each {label} set-operation "
                "branch as a SELECT query"
            )
        return (_extract_select_names(expression=expression, file_label=file_label, label=label),)
    raise CompileInputError(
        f"SQL test '{file_label}' must define each {label} set-operation branch as a SELECT query"
    )


def _is_synthetic_values_set_branch(expression: Any) -> bool:
    """Recognize Polyglot's SELECT wrapper around a VALUES set operand."""

    projections: tuple[Any, ...] = tuple(expression.expressions)
    if len(projections) != 1 or not projections[0].is_star:
        return False
    values_expression: Any | None = expression.find(_POLYGLOT_VALUES_EXPRESSION_NAME)
    if values_expression is None:
        return False
    alias: object = values_expression.args.get("alias")
    return isinstance(alias, dict) and alias.get("name") == _POLYGLOT_VALUES_SET_ALIAS


def _unwrap_expression(*, expression: Any) -> Any:
    while expression.__class__.__name__ in POLYGLOT_WRAPPER_EXPRESSION_NAMES:
        expression = expression.this
    return expression


def _extract_select_names(*, expression: Any, file_label: str, label: str) -> tuple[str, ...]:
    names: list[str] = []
    projection: Any
    for projection in expression.expressions:
        if projection.is_star:
            raise CompileInputError(
                f"SQL test '{file_label}' must not use SELECT * in {label} CTEs"
            )
        alias_name: str = str(projection.alias or "")
        if alias_name:
            names.append(alias_name)
            continue
        if projection.__class__.__name__ == POLYGLOT_COLUMN_EXPRESSION_NAME:
            names.append(str(projection.name))
            continue
        raise CompileInputError(
            f"SQL test '{file_label}' must alias every non-trivial {label} projection"
        )
    if not names:
        raise CompileInputError(
            f"SQL test '{file_label}' must project at least one column in {label}"
        )
    return tuple(names)
