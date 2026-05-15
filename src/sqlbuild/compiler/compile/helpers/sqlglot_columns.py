"""Optional SQLGlot-backed output column inference from model query SQL."""

from __future__ import annotations

import re
from typing import Any

from sqlbuild.adapter.shared.models import ExpressionInferenceProfile
from sqlbuild.adapter.shared.types import FunctionNullabilityRule
from sqlbuild.compiler.compile.models.core import InferredColumn
from sqlbuild.compiler.lineage.types import InferredNullability
from sqlbuild.shared.helpers.sql_reference_patterns import (
    quoted_reference_call_pattern,
    reference_call_prefix_pattern_text,
)
from sqlbuild.shared.helpers.sqlglot import import_sqlglot, import_sqlglot_expressions
from sqlbuild.shared.types import SqlReferenceKind

_REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.REF)
_SEED_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SEED)
_SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)
_DBT_REF_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.DBT_REF)
_UDF_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.UDF)}"
    r'"([A-Za-z_][A-Za-z0-9_]*)"\)\s*(?=\()'
)
_TABLE_FUNCTION_PATTERN: re.Pattern[str] = re.compile(
    rf"{reference_call_prefix_pattern_text(SqlReferenceKind.TABLE_FUNCTION)}"
    r'"([A-Za-z_][A-Za-z0-9_]*)"\)\s*(?=\()'
)
_PLACEHOLDER_PATTERN: re.Pattern[str] = re.compile(r"@@@(\w+)")


def infer_columns_with_sqlglot(
    *,
    query_sql: str,
    placeholders: dict[str, str] | None = None,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]] | None = None,
    inference_profile: ExpressionInferenceProfile | None = None,
) -> tuple[InferredColumn, ...] | None:
    """Infer output columns from model query SQL using SQLGlot.

    Returns None if SQLGlot is not available or the SQL cannot be parsed.
    Returns an empty tuple if the outermost SELECT uses SELECT * with no
    extractable column names.
    """

    sqlglot_module: Any | None = import_sqlglot()
    expressions_module: Any | None = import_sqlglot_expressions()
    if sqlglot_module is None or expressions_module is None:
        return None
    profile: ExpressionInferenceProfile = inference_profile or ExpressionInferenceProfile()

    cleaned_sql: str = _replace_refs_with_stubs(query_sql)
    if placeholders:
        cleaned_sql = substitute_placeholder_defaults(cleaned_sql, placeholders)

    try:
        parsed: Any = sqlglot_module.parse_one(cleaned_sql, dialect=profile.sqlglot_dialect)
    except Exception:
        return None

    infer_nullability: bool = not _is_set_operation(
        parsed=parsed, expressions_module=expressions_module
    )
    select: Any | None = _find_outermost_select(
        parsed=parsed, expressions_module=expressions_module
    )
    if select is None:
        return None

    return _extract_columns_from_select(
        select=select,
        expressions_module=expressions_module,
        column_nullability_by_table=column_nullability_by_table or {},
        infer_nullability=infer_nullability,
        inference_profile=profile,
    )


def substitute_placeholder_defaults(query_sql: str, placeholders: dict[str, str]) -> str:
    """Replace @@@name tokens with their default values for SQLGlot parsing."""

    if not placeholders:
        return query_sql

    def _replacer(match: re.Match[str]) -> str:
        name: str = match.group(1)
        return placeholders.get(name, match.group(0))

    return _PLACEHOLDER_PATTERN.sub(_replacer, query_sql)


def _replace_refs_with_stubs(query_sql: str) -> str:
    """Replace SQLBuild marker calls with parseable SQL stubs."""

    result: str = _REF_PATTERN.sub(r"\1", query_sql)
    result = _SEED_PATTERN.sub(r"\1", result)
    result = _SOURCE_PATTERN.sub(r"\1", result)
    result = _DBT_REF_PATTERN.sub(r"\1", result)
    result = _UDF_PATTERN.sub(r"__sqlbuild_udf_\1", result)
    result = _TABLE_FUNCTION_PATTERN.sub(r"__sqlbuild_table_function_\1", result)
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


def _is_set_operation(*, parsed: Any, expressions_module: Any) -> bool:
    union_type: type[Any] = expressions_module.Union
    intersect_type: type[Any] = expressions_module.Intersect
    except_type: type[Any] = expressions_module.Except
    if isinstance(parsed, (union_type, intersect_type, except_type)):
        return True
    body: Any | None = getattr(parsed, "this", None)
    return isinstance(body, (union_type, intersect_type, except_type))


def _extract_columns_from_select(
    *,
    select: Any,
    expressions_module: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    infer_nullability: bool,
    inference_profile: ExpressionInferenceProfile,
) -> tuple[InferredColumn, ...]:
    """Extract output column names and types from a SELECT's projection list."""

    column_nullability_by_table = dict(column_nullability_by_table)
    star_type: type[Any] = expressions_module.Star
    alias_type: type[Any] = expressions_module.Alias
    column_type: type[Any] = expressions_module.Column
    cast_type: type[Any] = expressions_module.Cast
    try_cast_type: type[Any] = expressions_module.TryCast
    alias_nullability: dict[str, InferredNullability] = _alias_nullability_from_select(
        select=select,
        expressions_module=expressions_module,
        column_nullability_by_table=column_nullability_by_table,
    )

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

        nullability: InferredNullability = InferredNullability.UNKNOWN
        if infer_nullability:
            nullability = _infer_expression_nullability(
                expression=inner,
                expressions_module=expressions_module,
                alias_nullability=alias_nullability,
                column_nullability_by_table=column_nullability_by_table,
                inference_profile=inference_profile,
            )

        columns.append(InferredColumn(name=name, type=col_type, nullability=nullability))

    return tuple(columns)


def _infer_expression_nullability(
    *,
    expression: Any,
    expressions_module: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> InferredNullability:
    """Infer only nullability facts SQLBuild can prove statically."""

    literal_type: type[Any] = expressions_module.Literal
    null_type: type[Any] = expressions_module.Null
    column_type: type[Any] = expressions_module.Column
    cast_type: type[Any] = expressions_module.Cast
    try_cast_type: type[Any] = expressions_module.TryCast
    coalesce_type: type[Any] = expressions_module.Coalesce
    count_type: type[Any] = expressions_module.Count

    if isinstance(expression, null_type):
        return InferredNullability.NULLABLE
    if isinstance(expression, literal_type):
        return InferredNullability.NON_NULL
    if isinstance(expression, column_type):
        return _infer_column_nullability(
            column=expression,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
        )
    if isinstance(expression, cast_type):
        return _infer_expression_nullability(
            expression=expression.this,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
    if isinstance(expression, try_cast_type):
        return InferredNullability.UNKNOWN
    if isinstance(expression, count_type):
        return InferredNullability.NON_NULL
    if isinstance(expression, coalesce_type):
        return _infer_coalesce_nullability(
            expression=expression,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
    function_name: str = _expression_function_name(expression)
    rule: FunctionNullabilityRule | None = inference_profile.function_nullability_rule(
        function_name
    )
    if rule is None:
        return InferredNullability.UNKNOWN
    arg_nullabilities: tuple[InferredNullability, ...] = tuple(
        _infer_expression_nullability(
            expression=arg,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
        for arg in _expression_function_args(expression)
    )
    return rule(arg_nullabilities)


def _infer_column_nullability(
    *,
    column: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> InferredNullability:
    table_name: str = str(column.table or "")
    column_name: str = str(column.name or "")
    if table_name:
        table_fact: InferredNullability = alias_nullability.get(
            table_name, InferredNullability.UNKNOWN
        )
        if table_fact == InferredNullability.NULLABLE:
            return InferredNullability.NULLABLE
        return column_nullability_by_table.get(table_name, {}).get(
            column_name, InferredNullability.UNKNOWN
        )

    matches: list[InferredNullability] = [
        column_facts[column_name]
        for column_facts in column_nullability_by_table.values()
        if column_name in column_facts
    ]
    if len(matches) == 1:
        return matches[0]
    return InferredNullability.UNKNOWN


def _infer_coalesce_nullability(
    *,
    expression: Any,
    expressions_module: Any,
    alias_nullability: dict[str, InferredNullability],
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
    inference_profile: ExpressionInferenceProfile,
) -> InferredNullability:
    arg_nullabilities: tuple[InferredNullability, ...] = tuple(
        _infer_expression_nullability(
            expression=arg,
            expressions_module=expressions_module,
            alias_nullability=alias_nullability,
            column_nullability_by_table=column_nullability_by_table,
            inference_profile=inference_profile,
        )
        for arg in expression.expressions
    )
    if any(value == InferredNullability.NON_NULL for value in arg_nullabilities):
        return InferredNullability.NON_NULL
    if arg_nullabilities and all(
        value == InferredNullability.NULLABLE for value in arg_nullabilities
    ):
        return InferredNullability.NULLABLE
    return InferredNullability.UNKNOWN


def _expression_function_name(expression: Any) -> str:
    sql_name: object | None = getattr(expression, "sql_name", None)
    if callable(sql_name):
        return str(sql_name()).upper()
    key: object | None = getattr(expression, "key", None)
    return str(key or "").upper()


def _expression_function_args(expression: Any) -> tuple[Any, ...]:
    args: list[Any] = []
    primary_arg: Any | None = getattr(expression, "this", None)
    if primary_arg is not None:
        args.append(primary_arg)
    args.extend(expression.expressions)
    return tuple(args)


def _alias_nullability_from_select(
    *,
    select: Any,
    expressions_module: Any,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> dict[str, InferredNullability]:
    table_type: type[Any] = expressions_module.Table
    alias_nullability: dict[str, InferredNullability] = {}
    current_aliases: set[str] = set()

    from_expression: Any | None = select.args.get("from_")
    from_table: Any | None = getattr(from_expression, "this", None)
    if isinstance(from_table, table_type):
        alias: str = _table_alias_or_name(from_table)
        current_aliases.add(alias)
        alias_nullability[alias] = InferredNullability.UNKNOWN
        _copy_table_facts_to_alias(
            alias=alias,
            table_name=from_table.name,
            column_nullability_by_table=column_nullability_by_table,
        )

    for join in select.args.get("joins") or []:
        joined_table: Any | None = join.this
        if not isinstance(joined_table, table_type):
            continue
        joined_alias: str = _table_alias_or_name(joined_table)
        side: str = str(join.args.get("side") or "").upper()
        if side == "LEFT":
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        elif side == "RIGHT":
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        elif side == "FULL":
            for alias in current_aliases:
                alias_nullability[alias] = InferredNullability.NULLABLE
            alias_nullability[joined_alias] = InferredNullability.NULLABLE
        else:
            alias_nullability[joined_alias] = InferredNullability.UNKNOWN
        current_aliases.add(joined_alias)
        _copy_table_facts_to_alias(
            alias=joined_alias,
            table_name=joined_table.name,
            column_nullability_by_table=column_nullability_by_table,
        )
    return alias_nullability


def _table_alias_or_name(table: Any) -> str:
    return str(table.alias_or_name or table.name)


def _copy_table_facts_to_alias(
    *,
    alias: str,
    table_name: str,
    column_nullability_by_table: dict[str, dict[str, InferredNullability]],
) -> None:
    if alias == table_name:
        return
    table_facts: dict[str, InferredNullability] | None = column_nullability_by_table.get(table_name)
    if table_facts is not None:
        column_nullability_by_table.setdefault(alias, table_facts)
