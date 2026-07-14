from __future__ import annotations

from collections.abc import Callable
from types import MappingProxyType
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter


class RecordingCursor:
    def __init__(self, rows: tuple[tuple[Any, ...], ...] = ()) -> None:
        self.rows: tuple[tuple[Any, ...], ...] = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return next(iter(self.rows), None)

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class RecordingConnection:
    def __init__(self, rows: tuple[tuple[Any, ...], ...] = ()) -> None:
        self.rows: tuple[tuple[Any, ...], ...] = rows
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> RecordingCursor:
        self.executed_sql.append(sql)
        return RecordingCursor(self.rows)


class RecordingBaseAdapter(BaseAdapter):
    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def execute(self, connection: object, sql: str) -> object:
        _CONNECTION_VALIDATORS[isinstance(connection, RecordingConnection)](connection)
        recording_connection: RecordingConnection = cast(RecordingConnection, connection)
        return recording_connection.execute(sql)

    def close(self, connection: object) -> None:
        del connection


def _accept_recording_connection(connection: object) -> None:
    del connection


def _reject_recording_connection(connection: object) -> None:
    del connection
    raise TypeError("expected RecordingConnection")


_CONNECTION_VALIDATORS: MappingProxyType[bool, Callable[[object], None]] = MappingProxyType(
    {False: _reject_recording_connection, True: _accept_recording_connection}
)
