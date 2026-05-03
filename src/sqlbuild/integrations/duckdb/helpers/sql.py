"""DuckDB SQL generation helpers."""

from __future__ import annotations

import logging
from typing import Any

from sqlbuild.adapter.shared.models import ColumnInfo, CursorValue
from sqlbuild.shared.helpers.diagnostics_logging import log_sql


def build_attach_sql(attach_entry: dict[str, object]) -> str:
    """Build an ATTACH statement from one attach config entry."""

    path: str = str(attach_entry["path"])
    sql: str = f"ATTACH '{path}'"
    alias: object | None = attach_entry.get("alias")
    if alias is not None:
        sql += f" AS {alias}"
    options: list[str] = []
    attach_type: object | None = attach_entry.get("type")
    if attach_type is not None:
        options.append(f"TYPE {attach_type}")
    read_only: object | None = attach_entry.get("read_only")
    if read_only is True:
        options.append("READ_ONLY")
    if options:
        sql += f" ({', '.join(options)})"
    return sql


def describe_relation(connection: Any, relation: str) -> tuple[ColumnInfo, ...]:
    """Return column metadata for a relation using DESCRIBE."""

    sql: str = f"DESCRIBE {relation}"
    log_sql(logger=logging.getLogger("sqlbuild.adapter.duckdb"), sql=sql)
    rows: list[tuple[Any, ...]] = connection.execute(sql).fetchall()
    return tuple(ColumnInfo(name=row[0], type=row[1]) for row in rows)


def query_column_names(connection: Any, sql: str) -> list[str]:
    """Return column names produced by a SQL query without materializing rows."""

    describe_sql: str = f"DESCRIBE SELECT * FROM ({sql}) AS __describe_source"
    log_sql(logger=logging.getLogger("sqlbuild.adapter.duckdb"), sql=describe_sql)
    rows: list[tuple[Any, ...]] = connection.execute(describe_sql).fetchall()
    return [row[0] for row in rows]


def build_cursor_filter(
    *,
    cursor_column: str | None,
    start_cursor: CursorValue | None,
    end_cursor: CursorValue | None,
) -> str:
    """Build a WHERE clause fragment for cursor-bounded queries."""

    if cursor_column is None or start_cursor is None:
        return ""
    clauses: list[str] = [f"{cursor_column} >= '{start_cursor.value}'"]
    if end_cursor is not None:
        clauses.append(f"{cursor_column} < '{end_cursor.value}'")
    return " AND ".join(clauses)
