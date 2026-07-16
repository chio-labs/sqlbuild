"""Helpers for Databricks adapter unit tests."""

from __future__ import annotations

from typing import Any


class FakeDatabricksMetadataCursor:
    def __init__(self, *, rows: list[tuple[object, ...]] | None = None) -> None:
        self.rows: list[tuple[object, ...]] = rows or []
        self.executed_sql: str | None = None
        self.closed: bool = False

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def close(self) -> None:
        self.closed = True


class FailingDatabricksMetadataCursor(FakeDatabricksMetadataCursor):
    def __init__(self, *, execute_error: Exception) -> None:
        super().__init__()
        self.execute_error = execute_error

    def execute(self, sql: str) -> None:
        self.executed_sql = sql
        raise self.execute_error


class FakeDatabricksMetadataConnection:
    def __init__(self, cursors: tuple[FakeDatabricksMetadataCursor, ...]) -> None:
        self._cursors: list[FakeDatabricksMetadataCursor] = list(cursors)
        self.returned_cursors: list[FakeDatabricksMetadataCursor] = []

    def cursor(self) -> Any:
        cursor: FakeDatabricksMetadataCursor = self._cursors.pop(0)
        self.returned_cursors.append(cursor)
        return cursor
