"""Cursor helpers for source loader writes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.executor.exceptions import ExecutorInputError


def load_staging_cursor_bounds(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging: str,
    cursor_column: str,
    statement_recorder: StatementRecorder,
) -> tuple[object | None, object | None]:
    quoted_cursor_column: str = adapter.render_identifier(cursor_column)
    sql: str = f"SELECT MIN({quoted_cursor_column}), MAX({quoted_cursor_column}) FROM {staging}"
    statement_recorder.record(sql)
    cursor: Any = adapter.execute(connection=connection, sql=sql)
    row: object | None = cursor.fetchone()
    if row is None:
        return (None, None)
    return (row[0], row[1])


def exclusive_cursor_end(value: object) -> object:
    if isinstance(value, bool):
        raise ExecutorInputError("delete_insert cursor bounds do not support boolean values")
    if isinstance(value, int):
        return value + 1
    if isinstance(value, datetime):
        return value + timedelta(microseconds=1)
    if isinstance(value, date):
        return value + timedelta(days=1)
    return value


def format_cursor_bound(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return str(value)
