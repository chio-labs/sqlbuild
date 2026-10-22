"""Recall store operations on ClickHouse connections, reached by native code through handles."""

from __future__ import annotations

import datetime
import json
import threading
from typing import Any

from sqlbuild.adapters.clickhouse._helpers.connect_clickhouse import connect_clickhouse
from sqlbuild.adapters.clickhouse.classes.clickhouse_connection import _ClickHouseConnection
from sqlbuild.adapters.clickhouse.classes.shared_recall_connections import (
    SharedRecallConnections,
)
from sqlbuild.adapters.clickhouse.types import RecallCell, RecallFailure, RecallStatistics

_CLIENT_MODULE: str = "clickhouse_connect"
_CONNECT_TIMEOUT_KEY: str = "connect_timeout"
_DEFAULT_CONNECT_TIMEOUT_SECONDS: int = 3
_TIMESTAMP_FORMAT: str = "%Y-%m-%dT%H:%M:%S.%fZ"
_BYTES_FORMATS: dict[str, str] = {"String": "bytes", "FixedString": "bytes"}
_ROW_BINARY: str = "RowBinary"
_INT64_MIN: int = -(2**63)
_INT64_MAX: int = 2**63 - 1
_READONLY_SETTING: str = "readonly"
_WRITABLE_READONLY_VALUE: str = "0"
_LIMIT_SETTING: str = "limit"


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
    *, config: dict[str, object], quiet_thread_attribute: str | None, read_only: bool
) -> tuple[RecallFailure, int]:
    """Connect for Recall; a `read_only` connection skips session settings under `readonly = 1`."""

    if quiet_thread_attribute is not None:
        setattr(threading.current_thread(), quiet_thread_attribute, True)
    options: dict[str, object] = {_CONNECT_TIMEOUT_KEY: _DEFAULT_CONNECT_TIMEOUT_SECONDS, **config}
    try:
        connection: _ClickHouseConnection = connect_clickhouse(
            config=options, settings_if_allowed=read_only
        )
    except Exception as error:
        return _failure(error), 0
    return None, SharedRecallConnections.connections.add(connection=connection)


def _server_value(*, client: Any, name: str) -> tuple[str | None, bool]:
    """The session's value of setting `name`, and whether this user may change it."""

    setting: Any = client.server_settings.get(name)
    if setting is None:
        return None, True
    return str(setting.value), not setting.readonly


def _query_settings(
    *, client: Any, settings: dict[str, int], row_cap: int | None
) -> tuple[dict[str, int], str | None]:
    """The settings the session does not already hold, or why the user may not set one."""

    sent: dict[str, int] = {}
    for name, value in settings.items():
        current, writable = _server_value(client=client, name=name)
        if current == str(value) or (
            name == _READONLY_SETTING and current not in (None, _WRITABLE_READONLY_VALUE)
        ):
            continue
        if not writable:
            return {}, (
                f"this ClickHouse user may not change the setting `{name}`, which Recall "
                f"queries set to {value}; set it in the user's settings profile, or give the "
                "user `readonly = 2`, which keeps it read-only and lets it set query settings"
            )
        sent[name] = value
    if row_cap is not None and _server_value(client=client, name=_LIMIT_SETTING)[1]:
        sent[_LIMIT_SETTING] = row_cap
    return sent, None


def run_recall_query(
    *, handle: int, sql: str, settings: dict[str, int], row_cap: int | None
) -> tuple[RecallFailure, tuple[list[str], list[list[RecallCell]], RecallStatistics] | None]:
    """Columns, at most `row_cap` rows of plain values, and server statistics."""

    try:
        client: Any = SharedRecallConnections.connections.get(handle=handle).client
        sent, refused = _query_settings(client=client, settings=settings, row_cap=row_cap)
        if refused is not None:
            return (False, refused), None
        rows: list[list[RecallCell]] = []
        with client.query_row_block_stream(
            sql, settings=sent, query_formats=_BYTES_FORMATS
        ) as stream:
            result: Any = stream.source
            for block in stream:
                rows.extend(_row(row) for row in block)
                if row_cap is not None and len(rows) >= row_cap:
                    break
            columns: list[str] = list(result.column_names)
            summary: dict[str, Any] = dict(result.summary or {})
    except Exception as error:
        return _failure(error), None
    statistics: RecallStatistics = (
        _number(summary=summary, key="read_rows"),
        _number(summary=summary, key="read_bytes"),
        summary.get("query_id"),
    )
    return None, (columns, rows[:row_cap] if row_cap is not None else rows, statistics)


def run_recall_command(*, handle: int, sql: str) -> tuple[RecallFailure, None]:
    """Run one DDL statement."""

    try:
        SharedRecallConnections.connections.get(handle=handle).client.command(sql)
    except Exception as error:
        return _failure(error), None
    return None, None


def insert_recall_rows(
    *, handle: int, table: str, column_names: list[str], payload: bytes, deduplication_token: str
) -> tuple[RecallFailure, None]:
    """Insert one `RowBinary` block; a retried block with the same token is deduplicated."""

    try:
        SharedRecallConnections.connections.get(handle=handle).client.raw_insert(
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

    connection: _ClickHouseConnection | None = SharedRecallConnections.connections.pop(
        handle=handle
    )
    if connection is None:
        return
    try:
        connection.close()
    except Exception:
        return
