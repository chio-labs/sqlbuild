from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Protocol, cast


class AdapterRecordingConnection(Protocol):
    def recorded_sql(self) -> tuple[str, ...]: ...

    def closed_cursor_count(self) -> int: ...


class AdapterCursorMaxCursor:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.rows: tuple[tuple[object, ...], ...] = rows
        self.closed: bool = False
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> None:
        self.executed_sql.append(sql)

    def fetchone(self) -> tuple[object, ...] | None:
        return next(iter(self.rows), None)

    def close(self) -> None:
        self.closed = True


class AdapterExecuteRecordingConnection:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.cursor: AdapterCursorMaxCursor = AdapterCursorMaxCursor(rows=rows)
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> AdapterCursorMaxCursor:
        self.executed_sql.append(sql)
        return self.cursor

    def recorded_sql(self) -> tuple[str, ...]:
        return tuple(self.executed_sql)

    def closed_cursor_count(self) -> int:
        return 0


class AdapterCursorRecordingConnection:
    def __init__(self, rows: tuple[tuple[object, ...], ...]) -> None:
        self.cursor_instance: AdapterCursorMaxCursor = AdapterCursorMaxCursor(rows=rows)

    def cursor(self) -> AdapterCursorMaxCursor:
        return self.cursor_instance

    def recorded_sql(self) -> tuple[str, ...]:
        return tuple(self.cursor_instance.executed_sql)

    def closed_cursor_count(self) -> int:
        return int(self.cursor_instance.closed)


def adapter_cursor_executed_sql(connection: object) -> tuple[str, ...]:
    _CONNECTION_VALIDATORS[
        isinstance(
            connection, (AdapterExecuteRecordingConnection, AdapterCursorRecordingConnection)
        )
    ](connection)
    return cast(AdapterRecordingConnection, connection).recorded_sql()


def adapter_closed_cursor_count(connection: object) -> int:
    _CONNECTION_VALIDATORS[
        isinstance(
            connection, (AdapterExecuteRecordingConnection, AdapterCursorRecordingConnection)
        )
    ](connection)
    return cast(AdapterRecordingConnection, connection).closed_cursor_count()


def _accept_recording_connection(connection: object) -> None:
    del connection


def _reject_recording_connection(connection: object) -> None:
    raise TypeError(f"unsupported connection type: {type(connection).__name__}")


_CONNECTION_VALIDATORS: MappingProxyType[bool, Callable[[object], None]] = MappingProxyType(
    {False: _reject_recording_connection, True: _accept_recording_connection}
)
