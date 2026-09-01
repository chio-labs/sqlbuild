"""Source reference resolution with optional type enforcement CAST wrapping."""

from __future__ import annotations

import re

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapter.type_system.main.types_equal import types_equal
from sqlbuild.compiler.planner.constants import (
    SOURCE_ALIAS_BOUNDARY_CHARACTERS,
    SQL_ALIAS_KEYWORD,
    SQL_BRACKETED_IDENTIFIER_START,
    SQL_QUOTED_IDENTIFIER_DELIMITERS,
)
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.references.main._quoted_reference_call_pattern import (
    quoted_reference_call_pattern,
)
from sqlbuild.compiler.references.main._render_source_relation import render_source_relation
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SourceColumnEntry, SourceEntry

_SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)
_DERIVED_TABLE_ALIAS_KEYWORDS: frozenset[str] = frozenset(
    {
        "APPLY",
        "CROSS",
        "EXCEPT",
        "FULL",
        "GROUP",
        "HAVING",
        "INNER",
        "INTERSECT",
        "JOIN",
        "LEFT",
        "LIMIT",
        "OFFSET",
        "ON",
        "ORDER",
        "OUTER",
        "RIGHT",
        "UNION",
        "WHERE",
    }
)


def resolve_source_references(
    *,
    query_sql: str,
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    cursor_bounds: CursorBounds | None,
    cursor_filter_inputs: dict[str, str],
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
) -> str:
    """Replace all __source() calls in query SQL with resolved names or CAST subqueries."""

    def _replacement(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        return _resolve_source_reference(
            source_name=source_name,
            source_map=source_map,
            source_warehouse_columns=source_warehouse_columns,
            cursor_bounds=cursor_bounds,
            cursor_filter_inputs=cursor_filter_inputs,
            adapter=adapter,
            cursor_type=cursor_type,
            lower_bound_inclusive=lower_bound_inclusive,
            unknown_source_sql=match.group(0),
        )

    if not adapter.requires_derived_table_aliases():
        return _SOURCE_PATTERN.sub(_replacement, query_sql)

    resolved_chunks: list[str] = []
    cursor: int = 0
    for match in _SOURCE_PATTERN.finditer(query_sql):
        source_name: str = match.group(1)
        resolved_source: str = _resolve_source_reference(
            source_name=source_name,
            source_map=source_map,
            source_warehouse_columns=source_warehouse_columns,
            cursor_bounds=cursor_bounds,
            cursor_filter_inputs=cursor_filter_inputs,
            adapter=adapter,
            cursor_type=cursor_type,
            lower_bound_inclusive=lower_bound_inclusive,
            unknown_source_sql=match.group(0),
        )
        alias_span: tuple[int, str | None] = (match.end(), None)
        if _is_derived_table_factor(resolved_source):
            alias_span = _consume_source_alias(query_sql=query_sql, start=match.end())
            alias: str = alias_span[1] or _internal_source_alias(source_name)
            resolved_source = f"{resolved_source} AS {alias}"
        resolved_chunks.append(query_sql[cursor : match.start()])
        resolved_chunks.append(resolved_source)
        cursor = alias_span[0]
    resolved_chunks.append(query_sql[cursor:])
    return "".join(resolved_chunks)


def _resolve_source_reference(
    *,
    source_name: str,
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    cursor_bounds: CursorBounds | None,
    cursor_filter_inputs: dict[str, str],
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
    unknown_source_sql: str,
) -> str:
    source_entry: SourceEntry | None = source_map.get(source_name)
    if source_entry is None:
        return unknown_source_sql
    resolved_source: str = _render_source_relation(adapter=adapter, source_entry=source_entry)
    warehouse_cols: tuple[ColumnInfo, ...] | None = source_warehouse_columns.get(source_name)
    if source_entry.expression is None and warehouse_cols:
        _validate_declared_columns(
            qualified_name=resolved_source,
            declared_columns=source_entry.columns,
            available_columns=warehouse_cols,
            contract_enforced=source_entry.contract == ContractPolicy.ENFORCED,
            dialect=adapter.sql_analysis_dialect_name,
        )
    if (
        source_entry.expression is not None
        and warehouse_cols
        and source_entry.contract == ContractPolicy.ENFORCED
    ):
        _validate_declared_columns(
            qualified_name=f"source expression '{source_name}'",
            declared_columns=source_entry.columns,
            available_columns=warehouse_cols,
            contract_enforced=source_entry.contract == ContractPolicy.ENFORCED,
            dialect=adapter.sql_analysis_dialect_name,
        )
    if source_entry.type_enforcement:
        if source_entry.expression is not None:
            resolved_source = _build_expression_cast_subquery(
                source_name=source_entry.name,
                source_relation=resolved_source,
                declared_columns=source_entry.columns,
                expression_columns=warehouse_cols,
                adapter=adapter,
            )
        elif warehouse_cols is not None and warehouse_cols:
            resolved_source = _build_relation_cast_subquery(
                qualified_name=resolved_source,
                declared_columns=source_entry.columns,
                warehouse_columns=warehouse_cols,
                adapter=adapter,
            )
    if cursor_bounds is None:
        return resolved_source
    cursor_column: str | None = cursor_filter_inputs.get(source_name)
    if cursor_column is None:
        return resolved_source
    return _build_cursor_subquery(
        resolved_source=resolved_source,
        cursor_column=cursor_column,
        bounds=cursor_bounds,
        adapter=adapter,
        cursor_type=cursor_type,
        lower_bound_inclusive=lower_bound_inclusive,
    )


def _is_derived_table_factor(source_sql: str) -> bool:
    return source_sql.lstrip().startswith("(")


def _consume_source_alias(*, query_sql: str, start: int) -> tuple[int, str | None]:
    index: int = _skip_whitespace(query_sql=query_sql, start=start)
    token_end: int
    token: str | None
    token_end, token = _read_alias_token(query_sql=query_sql, start=index)
    if token is None:
        return start, None
    if token.upper() == SQL_ALIAS_KEYWORD:
        alias_start: int = _skip_whitespace(query_sql=query_sql, start=token_end)
        alias_end: int
        alias: str | None
        alias_end, alias = _read_alias_token(query_sql=query_sql, start=alias_start)
        if alias is None or _is_alias_keyword(alias):
            return start, None
        return alias_end, alias
    if _is_alias_keyword(token):
        return start, None
    return token_end, token


def _skip_whitespace(*, query_sql: str, start: int) -> int:
    index: int = start
    while index < len(query_sql) and query_sql[index].isspace():
        index += 1
    return index


def _read_alias_token(*, query_sql: str, start: int) -> tuple[int, str | None]:
    if start >= len(query_sql):
        return start, None
    first_char: str = query_sql[start]
    if first_char in SOURCE_ALIAS_BOUNDARY_CHARACTERS:
        return start, None
    if first_char == SQL_BRACKETED_IDENTIFIER_START:
        end_bracket: int = query_sql.find("]", start + 1)
        if end_bracket == -1:
            return start, None
        return end_bracket + 1, query_sql[start : end_bracket + 1]
    if first_char in SQL_QUOTED_IDENTIFIER_DELIMITERS:
        end_quote: int = query_sql.find(first_char, start + 1)
        if end_quote == -1:
            return start, None
        return end_quote + 1, query_sql[start : end_quote + 1]
    match: re.Match[str] | None = re.match(r"[A-Za-z_][A-Za-z0-9_$]*", query_sql[start:])
    if match is None:
        return start, None
    return start + match.end(), match.group(0)


def _is_alias_keyword(token: str) -> bool:
    return token.upper() in _DERIVED_TABLE_ALIAS_KEYWORDS


def _internal_source_alias(source_name: str) -> str:
    alias_suffix: str = re.sub(r"[^A-Za-z0-9_]+", "_", source_name).strip("_").lower()
    if not alias_suffix:
        alias_suffix = "source"
    return f"__sqb_source_{alias_suffix}"


def _render_source_relation(*, adapter: BaseAdapter, source_entry: SourceEntry) -> str:
    if source_entry.expression is not None:
        return render_source_relation(entry=source_entry, adapter=adapter)
    table_name: str = source_entry.table if source_entry.table is not None else source_entry.name
    rendered: str | None = adapter.render_qualified_name(
        database=source_entry.database,
        schema=source_entry.schema,
        name=table_name,
    )
    if rendered is not None:
        return rendered
    return render_source_relation(entry=source_entry)


def _build_relation_cast_subquery(
    *,
    qualified_name: str,
    declared_columns: tuple[SourceColumnEntry, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
    adapter: BaseAdapter,
) -> str:
    """Build a CAST subquery for type-enforced sources."""

    enforced_map: dict[str, str] = {
        col.name: col.type for col in declared_columns if col.type is not None
    }
    if not enforced_map:
        return qualified_name

    warehouse_names: set[str] = {col.name for col in warehouse_columns}
    cast_names: list[str] = [name for name in enforced_map if name in warehouse_names]
    if not cast_names:
        return qualified_name

    cast_expressions: tuple[str, ...] = tuple(
        adapter.render_source_expression_cast(
            expression=name,
            target_type=enforced_map[name],
            alias=name,
        )
        for name in cast_names
    )
    all_enforced: bool = len(cast_names) == len(warehouse_names)
    return adapter._render_source_relation_cast_subquery_with_columns(
        source_relation=qualified_name,
        cast_projections=cast_expressions,
        cast_column_names=tuple(cast_names),
        warehouse_column_names=tuple(col.name for col in warehouse_columns),
        all_columns_cast=all_enforced,
    )


def _validate_declared_columns(
    *,
    qualified_name: str,
    declared_columns: tuple[SourceColumnEntry, ...],
    available_columns: tuple[ColumnInfo, ...],
    contract_enforced: bool = False,
    dialect: str | None = None,
) -> None:
    """Ensure declared source columns exist and enforced contracts match metadata."""

    available_by_name: dict[str, ColumnInfo] = {col.name.lower(): col for col in available_columns}
    missing_names: tuple[str, ...] = tuple(
        col.name for col in declared_columns if col.name.lower() not in available_by_name
    )
    if missing_names:
        missing_columns: str = ", ".join(missing_names)
        raise PlannerInputError(
            f"source {qualified_name} declares columns not found in warehouse: {missing_columns}",
            code="S401",
        )

    if not contract_enforced:
        return

    declared_column: SourceColumnEntry
    for declared_column in declared_columns:
        if declared_column.type is None:
            continue
        available_column: ColumnInfo = available_by_name[declared_column.name.lower()]
        if not available_column.type:
            continue
        if types_equal(left=available_column.type, right=declared_column.type, dialect=dialect):
            continue
        raise PlannerInputError(
            f"source {qualified_name} column '{declared_column.name}' has type "
            f"{available_column.type} but contract declares {declared_column.type}",
            code="S404",
        )


def _build_expression_cast_subquery(
    *,
    source_name: str,
    source_relation: str,
    declared_columns: tuple[SourceColumnEntry, ...],
    expression_columns: tuple[ColumnInfo, ...] | None,
    adapter: BaseAdapter,
) -> str:
    """Build a CAST projection for expression sources using probed column names."""

    enforced_map: dict[str, str] = {
        col.name: col.type for col in declared_columns if col.type is not None
    }
    if not enforced_map:
        return source_relation
    if expression_columns is None:
        raise PlannerInputError(
            f"source expression '{source_name}' type enforcement requires query output "
            "column metadata",
            code="S402",
        )

    expression_names: tuple[str, ...] = tuple(col.name for col in expression_columns)
    expression_name_map: dict[str, str] = {name.lower(): name for name in expression_names}
    missing_names: tuple[str, ...] = tuple(
        col.name for col in declared_columns if col.name.lower() not in expression_name_map
    )
    if missing_names:
        missing_columns: str = ", ".join(missing_names)
        available_columns: str = ", ".join(expression_names) if expression_names else "<none>"
        raise PlannerInputError(
            f"source expression '{source_name}' declares columns not found in query output: "
            f"{missing_columns}. Available query output columns: {available_columns}",
            code="S403",
        )

    projections: list[str] = _build_expression_source_projections(
        expression_names=expression_names,
        declared_columns=declared_columns,
        expression_name_map=expression_name_map,
        adapter=adapter,
    )
    return adapter.render_source_expression_cast_subquery(
        source_relation=source_relation,
        projections=tuple(projections),
    )


def _build_expression_source_projections(
    *,
    expression_names: tuple[str, ...],
    declared_columns: tuple[SourceColumnEntry, ...],
    expression_name_map: dict[str, str],
    adapter: BaseAdapter,
) -> list[str]:
    enforced_map: dict[str, str] = {
        col.name: col.type for col in declared_columns if col.type is not None
    }
    enforced_by_expression_name: dict[str, tuple[str, str]] = {
        expression_name_map[name.lower()]: (name, column_type)
        for name, column_type in enforced_map.items()
        if name.lower() in expression_name_map
    }
    projections: list[str] = []
    for name in expression_names:
        enforced_entry: tuple[str, str] | None = enforced_by_expression_name.get(name)
        if enforced_entry is None:
            projections.append(name)
            continue
        declared_name: str
        column_type: str
        declared_name, column_type = enforced_entry
        projections.append(
            adapter.render_source_expression_cast(
                expression=name,
                target_type=column_type,
                alias=declared_name,
            )
        )
    return projections


def _build_cursor_subquery(
    *,
    resolved_source: str,
    cursor_column: str,
    bounds: CursorBounds,
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
) -> str:
    """Wrap a resolved source relation in a cursor-filtered subquery."""

    lower_operator: str = ">=" if lower_bound_inclusive else ">"
    start_literal: str = adapter.render_cursor_bound_literal(
        value=bounds.start, cursor_type=cursor_type
    )
    end_literal: str = adapter.render_cursor_bound_literal(
        value=bounds.end, cursor_type=cursor_type
    )
    return (
        f"(SELECT * FROM {resolved_source}"
        f" WHERE {cursor_column} {lower_operator} {start_literal}"
        f" AND {cursor_column} < {end_literal})"
    )
