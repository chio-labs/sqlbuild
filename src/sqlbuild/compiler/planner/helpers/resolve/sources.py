"""Source reference resolution with optional type enforcement CAST wrapping."""

from __future__ import annotations

import re

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.adapter.shared.type_normalization import types_equal
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.shared.helpers.sources import render_source_relation
from sqlbuild.shared.helpers.sql_reference_patterns import quoted_reference_call_pattern
from sqlbuild.shared.types import SqlReferenceKind
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry

_SOURCE_PATTERN: re.Pattern[str] = quoted_reference_call_pattern(SqlReferenceKind.SOURCE)


def resolve_source_references(
    *,
    query_sql: str,
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    cursor_bounds: CursorBounds | None,
    cursor_inputs: dict[str, str],
    adapter: BaseAdapter,
    cursor_type: str | None,
    lower_bound_inclusive: bool,
) -> str:
    """Replace all __source() calls in query SQL with resolved names or CAST subqueries."""

    def _replace_source(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        source_entry: SourceEntry | None = source_map.get(source_name)
        if source_entry is None:
            return match.group(0)
        resolved_source: str = _render_source_relation(adapter=adapter, source_entry=source_entry)
        warehouse_cols: tuple[ColumnInfo, ...] | None = source_warehouse_columns.get(source_name)
        if source_entry.expression is None and warehouse_cols:
            _validate_declared_columns(
                qualified_name=resolved_source,
                declared_columns=source_entry.columns,
                available_columns=warehouse_cols,
                contract_enforced=source_entry.contract == ContractPolicy.ENFORCED,
                dialect=adapter.sqlglot_dialect_name,
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
                dialect=adapter.sqlglot_dialect_name,
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
                    star_exclude_keyword=star_exclude_keyword,
                )
        if cursor_bounds is None:
            return resolved_source
        cursor_column: str | None = cursor_inputs.get(source_name)
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

    return _SOURCE_PATTERN.sub(_replace_source, query_sql)


def _render_source_relation(*, adapter: BaseAdapter, source_entry: SourceEntry) -> str:
    if source_entry.expression is not None:
        return render_source_relation(source_entry)
    table_name: str = source_entry.table if source_entry.table is not None else source_entry.name
    rendered: str | None = adapter.render_qualified_name(
        database=source_entry.database,
        schema=source_entry.schema,
        name=table_name,
    )
    if rendered is not None:
        return rendered
    return render_source_relation(source_entry)


def _build_relation_cast_subquery(
    *,
    qualified_name: str,
    declared_columns: tuple[SourceColumnEntry, ...],
    warehouse_columns: tuple[ColumnInfo, ...],
    star_exclude_keyword: str,
) -> str:
    """Build a CAST subquery using SELECT * EXCLUDE for type-enforced sources."""

    enforced_map: dict[str, str] = {
        col.name: col.type for col in declared_columns if col.type is not None
    }
    if not enforced_map:
        return qualified_name

    warehouse_names: set[str] = {col.name for col in warehouse_columns}
    cast_names: list[str] = [name for name in enforced_map if name in warehouse_names]
    if not cast_names:
        return qualified_name

    cast_expressions: list[str] = [
        f"CAST({name} AS {enforced_map[name]}) AS {name}" for name in cast_names
    ]
    cast_clause: str = ", ".join(cast_expressions)

    all_enforced: bool = len(cast_names) == len(warehouse_names)
    if all_enforced:
        return f"(SELECT {cast_clause} FROM {qualified_name})"

    exclude_list: str = ", ".join(cast_names)
    return (
        f"(SELECT * {star_exclude_keyword} ({exclude_list}), {cast_clause} FROM {qualified_name})"
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
    projection_clause: str = ", ".join(projections)
    return f"(SELECT {projection_clause} FROM {source_relation})"


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
    start_literal: str = adapter.render_cursor_bound_literal(bounds.start, cursor_type)
    end_literal: str = adapter.render_cursor_bound_literal(bounds.end, cursor_type)
    return (
        f"(SELECT * FROM {resolved_source}"
        f" WHERE {cursor_column} {lower_operator} {start_literal}"
        f" AND {cursor_column} < {end_literal})"
    )
