"""Source reference resolution with optional type enforcement CAST wrapping."""

from __future__ import annotations

import re

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry

_SOURCE_PATTERN: re.Pattern[str] = re.compile(r'__source\("([^"]+)"\)')


def resolve_source_references(
    *,
    query_sql: str,
    source_map: dict[str, SourceEntry],
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]],
    star_exclude_keyword: str,
    cursor_bounds: CursorBounds | None,
    cursor_inputs: dict[str, str],
) -> str:
    """Replace all __source() calls in query SQL with resolved names or CAST subqueries."""

    def _replace_source(match: re.Match[str]) -> str:
        source_name: str = match.group(1)
        source_entry: SourceEntry | None = source_map.get(source_name)
        if source_entry is None:
            return match.group(0)
        qualified_name: str = _build_source_qualified_name(source_entry)
        resolved_source: str = qualified_name
        warehouse_cols: tuple[ColumnInfo, ...] | None = source_warehouse_columns.get(source_name)
        if source_entry.type_enforcement and warehouse_cols is not None and warehouse_cols:
            resolved_source = _build_cast_subquery(
                qualified_name=qualified_name,
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
        )

    return _SOURCE_PATTERN.sub(_replace_source, query_sql)


def _build_source_qualified_name(entry: SourceEntry) -> str:
    """Build a qualified relation name from a source entry."""

    parts: list[str] = []
    if entry.database is not None:
        parts.append(entry.database)
    if entry.schema is not None:
        parts.append(entry.schema)
    table_name: str = entry.table if entry.table is not None else entry.name
    parts.append(table_name)
    return ".".join(parts)


def _build_cast_subquery(
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


def _build_cursor_subquery(
    *,
    resolved_source: str,
    cursor_column: str,
    bounds: CursorBounds,
) -> str:
    """Wrap a resolved source relation in a cursor-filtered subquery."""

    return (
        f"(SELECT * FROM {resolved_source}"
        f" WHERE {cursor_column} >= '{bounds.start}'"
        f" AND {cursor_column} < '{bounds.end}')"
    )
