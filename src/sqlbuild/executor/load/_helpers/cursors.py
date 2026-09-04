"""Cursor helpers for source loader writes."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.types import CursorKind
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.models import DateValue, IntegerValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar
from sqlbuild.errors.contracts.exceptions import ExecutorInputError


def load_staging_cursor_bounds(
    *,
    adapter: BaseAdapter,
    connection: Any,
    staging: str,
    cursor_column: str,
    statement_recorder: StatementRecorder,
) -> tuple[CursorScalar | None, CursorScalar | None]:
    quoted_cursor_column: str = adapter.render_identifier(cursor_column)
    sql: str = f"SELECT MIN({quoted_cursor_column}), MAX({quoted_cursor_column}) FROM {staging}"
    statement_recorder.record(sql)
    cursor: Any = adapter.execute(connection=connection, sql=sql)
    row: object | None = cursor.fetchone()
    if row is None:
        return (None, None)
    return (_parse_loader_cursor(value=row[0]), _parse_loader_cursor(value=row[1]))


def exclusive_cursor_end(value: CursorScalar) -> CursorScalar:
    if isinstance(value, IntegerValue):
        return IntegerValue(value=value.value + 1)
    if isinstance(value, TimestampValue):
        return TimestampValue(value=value.value + timedelta(microseconds=1))
    return DateValue(value=value.value + timedelta(days=1))


def infer_cursor_kind(value: object) -> CursorKind | None:
    if isinstance(value, IntegerValue) or isinstance(value, int) and not isinstance(value, bool):
        return CursorKind.INTEGER
    if isinstance(value, TimestampValue | datetime):
        return CursorKind.TIMESTAMP
    return None


def format_cursor_bound(value: CursorScalar) -> str:
    return render(value=value)


def _parse_loader_cursor(*, value: object | None) -> CursorScalar | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ExecutorInputError("delete_insert cursor bounds do not support boolean values")
    if isinstance(value, int | Decimal):
        return parse(raw=value, cursor_type="integer")
    if isinstance(value, date | datetime | str):
        return parse(raw=value, cursor_type="timestamp")
    raise ExecutorInputError(f"delete_insert cursor bounds do not support {type(value).__name__}")
