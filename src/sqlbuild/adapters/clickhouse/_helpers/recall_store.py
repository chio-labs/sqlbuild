"""Recall store operations on ClickHouse connections, reached by native code through handles."""

from __future__ import annotations

import datetime
import json
import threading
from typing import Any

from sqlbuild.adapters.clickhouse.classes.clickhouse_adapter import ClickHouseAdapter
from sqlbuild.adapters.clickhouse.classes.clickhouse_connection import _ClickHouseConnection
from sqlbuild.adapters.clickhouse.types import RecallCell, RecallFailure, RecallStatistics

_CLIENT_MODULE: str = "clickhouse_connect"
_CONNECT_TIMEOUT_KEY: str = "connect_timeout"
_DEFAULT_CONNECT_TIMEOUT_SECONDS: int = 3
_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"
_BYTES_FORMATS: dict[str, str] = {"String": "bytes", "FixedString": "bytes"}
_ROW_BINARY: str = "RowBinary"
_INT64_MIN: int = -(2**63)
_INT64_MAX: int = 2**63 - 1


def _failure(error: Exception) -> tuple[bool, str]:
    return (type(error).__module__.startswith(_CLIENT_MODULE), str(error))


def _cell(value: object) -> RecallCell:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if _INT64_MIN <= value <= _INT64_MAX else str(value)
    if value is None or isinstance(value, (float, str)):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return value
    if isinstance(value, datetime.datetime):
        return value.strftime(_TIMESTAMP_FORMAT)
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, default=_text)
    return str(value)


def _text(value: object) -> object:
    cell: RecallCell = _cell(value)
    return cell.hex() if isinstance(cell, bytes) else cell


def _row(row: Any) -> list[RecallCell]:
    return [_cell(value) for value in row]


def _number(*, summary: dict[str, Any], key: str) -> int | None:
    value: object = summary.get(key)
    return int(str(value)) if value is not None else None


def connect_recall_store(
    *, config: dict[str, object], quiet_thread_attribute: str | None
) -> tuple[RecallFailure, int]:
    """Connect for Recall and return the handle; only the delivery thread asks to stay quiet."""

    if quiet_thread_attribute is not None:
        setattr(threading.current_thread(), quiet_thread_attribute, True)
    options: dict[str, object] = {_CONNECT_TIMEOUT_KEY: _DEFAULT_CONNECT_TIMEOUT_SECONDS, **config}
    try:
        adapter: ClickHouseAdapter = ClickHouseAdapter()
        connection: _ClickHouseConnection = adapter.connect(options)
    except Exception as error:
        return _failure(error), 0
    return None, adapter.recall_connections.add(connection=connection)


def run_recall_query(
    *, handle: int, sql: str, settings: dict[str, int]
) -> tuple[RecallFailure, tuple[list[str], list[list[RecallCell]], RecallStatistics] | None]:
    """Columns, rows of plain values and server statistics; strings not in UTF-8 stay bytes."""

    try:
        result: Any = ClickHouseAdapter.recall_connections.get(handle=handle).client.query(
            sql, settings=settings, query_formats=_BYTES_FORMATS
        )
    except Exception as error:
        return _failure(error), None
    summary: dict[str, Any] = dict(result.summary or {})
    statistics: RecallStatistics = (
        _number(summary=summary, key="read_rows"),
        _number(summary=summary, key="read_bytes"),
        summary.get("query_id"),
    )
    rows: list[list[RecallCell]] = [_row(row) for row in result.result_rows]
    return None, (list(result.column_names), rows, statistics)


def run_recall_command(*, handle: int, sql: str) -> tuple[RecallFailure, None]:
    """Run one DDL statement."""

    try:
        ClickHouseAdapter.recall_connections.get(handle=handle).client.command(sql)
    except Exception as error:
        return _failure(error), None
    return None, None


def insert_recall_rows(
    *, handle: int, table: str, column_names: list[str], payload: bytes, deduplication_token: str
) -> tuple[RecallFailure, None]:
    """Insert one `RowBinary` block; a retried block with the same token is deduplicated."""

    try:
        ClickHouseAdapter.recall_connections.get(handle=handle).client.raw_insert(
            table,
            column_names=column_names,
            insert_block=payload,
            settings={"insert_deduplication_token": deduplication_token},
            fmt=_ROW_BINARY,
        )
    except Exception as error:
        return _failure(error), None
    return None, None


def close_recall_store(*, handle: int) -> None:
    """Close and forget the connection; a failure to close is ignored."""

    connection: _ClickHouseConnection | None = ClickHouseAdapter.recall_connections.pop(
        handle=handle
    )
    if connection is None:
        return
    try:
        connection.close()
    except Exception:
        return
