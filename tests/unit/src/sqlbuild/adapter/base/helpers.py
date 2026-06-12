from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter


class RecordingCursor:
    def __init__(self, rows: tuple[tuple[Any, ...], ...] = ()) -> None:
        self.rows: tuple[tuple[Any, ...], ...] = rows

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

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
        if not isinstance(connection, RecordingConnection):
            raise TypeError("expected RecordingConnection")
        return connection.execute(sql)

    def close(self, connection: object) -> None:
        del connection
