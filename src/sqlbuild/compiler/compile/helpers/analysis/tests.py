"""Optional Polyglot-backed SQL-native test helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.shared.helpers.sql.polyglot import import_polyglot_sql


def extract_expected_branch_column_names_with_sql_analysis(
    *, sql: str, file_label: str
) -> tuple[tuple[str, ...], ...] | None:
    """Return expected SELECT branch names using Polyglot when it is installed."""

    polyglot_module: Any | None = import_polyglot_sql()
    if polyglot_module is None:
        return None

    try:
        parsed_expression: Any = polyglot_module.parse_one(sql, dialect="generic")
    except Exception:
        branches: tuple[str, ...] = _split_set_operation_branches(sql)
        if len(branches) > 1:
            return tuple(
                _extract_branch_names(
                    expression=polyglot_module.parse_one(branch_sql, dialect="generic"),
                    file_label=file_label,
                )[0]
                for branch_sql in branches
            )
        return None
    return _extract_branch_names(expression=parsed_expression, file_label=file_label)


def _extract_branch_names(*, expression: Any, file_label: str) -> tuple[tuple[str, ...], ...]:
    expression = _unwrap_expression(expression=expression)
    if expression.__class__.__name__ == "Union":
        left_expression: Any = expression.args["left"]
        right_expression: Any = expression.args["right"]
        return (
            *_extract_branch_names(expression=left_expression, file_label=file_label),
            *_extract_branch_names(expression=right_expression, file_label=file_label),
        )
    if expression.__class__.__name__ == "Select":
        return (_extract_select_names(expression=expression, file_label=file_label),)
    raise CompileInputError(
        f"SQL test '{file_label}' must define each __expected__<model> set-operation "
        "branch as a SELECT query"
    )


def _unwrap_expression(*, expression: Any) -> Any:
    while expression.__class__.__name__ in {"Subquery", "Paren"}:
        expression = expression.this
    return expression


def _extract_select_names(*, expression: Any, file_label: str) -> tuple[str, ...]:
    names: list[str] = []
    projection: Any
    for projection in expression.expressions:
        if projection.is_star:
            raise CompileInputError(
                f"SQL test '{file_label}' must not use SELECT * in __expected__<model> CTEs"
            )
        alias_name: str = str(projection.alias or "")
        if alias_name:
            names.append(alias_name)
            continue
        if projection.__class__.__name__ == "Column":
            names.append(str(projection.name))
            continue
        raise CompileInputError(
            f"SQL test '{file_label}' must alias every non-trivial __expected__<model> projection"
        )
    if not names:
        raise CompileInputError(
            f"SQL test '{file_label}' must project at least one column in __expected__<model>"
        )
    return tuple(names)


def _split_set_operation_branches(sql: str) -> tuple[str, ...]:
    branches: list[str] = []
    branch_start: int = 0
    depth: int = 0
    quote: str | None = None
    index: int = 0
    while index < len(sql):
        character: str = sql[index]
        if quote is not None:
            if character == quote:
                quote = None
            index += 1
            continue
        if character in {"'", '"', "`"}:
            quote = character
            index += 1
            continue
        if character == "(":
            depth += 1
            index += 1
            continue
        if character == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        operation_end: int | None = _consume_set_operation(sql=sql, start=index)
        if depth == 0 and operation_end is not None:
            branch_sql: str = sql[branch_start:index].strip()
            if branch_sql:
                branches.append(branch_sql)
            branch_start = operation_end
            index = operation_end
            continue
        index += 1
    final_branch_sql: str = sql[branch_start:].strip()
    if final_branch_sql:
        branches.append(final_branch_sql)
    return tuple(branches)


def _consume_set_operation(*, sql: str, start: int) -> int | None:
    keyword: str
    for keyword in ("UNION", "INTERSECT", "EXCEPT"):
        end: int = start + len(keyword)
        if sql[start:end].upper() != keyword:
            continue
        if start > 0 and (sql[start - 1].isalnum() or sql[start - 1] == "_"):
            continue
        if end < len(sql) and (sql[end].isalnum() or sql[end] == "_"):
            continue
        index: int = _skip_whitespace(sql=sql, start=end)
        if keyword == "UNION" and sql[index : index + 3].upper() == "ALL":
            all_end: int = index + 3
            if all_end == len(sql) or not (sql[all_end].isalnum() or sql[all_end] == "_"):
                index = _skip_whitespace(sql=sql, start=all_end)
        return index
    return None


def _skip_whitespace(*, sql: str, start: int) -> int:
    while start < len(sql) and sql[start].isspace():
        start += 1
    return start
