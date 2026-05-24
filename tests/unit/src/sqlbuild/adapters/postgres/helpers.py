"""Helpers for Postgres adapter unit tests."""

from __future__ import annotations

from typing import Any


class FakePostgresCursor:
    """Cursor double matching the psycopg2 cursor interface."""

    def __init__(self, rows: tuple[tuple[Any, ...], ...] = ()) -> None:
        self.rows: tuple[tuple[Any, ...], ...] = rows
        self.executed_sql: str | None = None
        self.executemany_sql: str | None = None
        self.executemany_rows: list[tuple[object, ...]] = []
        self.closed: bool = False

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        self.executemany_sql = sql
        self.executemany_rows = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)

    def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    def close(self) -> None:
        self.closed = True


class FakePostgresConnection:
    """Connection double matching the _PostgresConnection interface."""

    def __init__(self, cursor: FakePostgresCursor) -> None:
        self._cursor: FakePostgresCursor = cursor
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> FakePostgresCursor:
        self.executed_sql.append(sql)
        return self._cursor

    def cursor(self) -> FakePostgresCursor:
        return self._cursor
