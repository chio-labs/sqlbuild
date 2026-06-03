"""Helpers for Snowflake adapter unit tests."""

from __future__ import annotations

from typing import Any


class FakeSnowflakeDescribeCursor:
    """Cursor double exposing Snowflake-style description metadata."""

    def __init__(self, description: tuple[tuple[str], ...]) -> None:
        self.description: tuple[tuple[str], ...] = description
        self.executed_sql: str | None = None
        self.executemany_sql: str | None = None
        self.executemany_rows: list[tuple[object, ...]] = []
        self.closed: bool = False

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def executemany(self, sql: str, rows: list[tuple[object, ...]]) -> None:
        self.executemany_sql = sql
        self.executemany_rows = rows

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeDescribeConnection:
    """Connection double returning a preconfigured describe cursor."""

    def __init__(self, cursor: FakeSnowflakeDescribeCursor) -> None:
        self._cursor: FakeSnowflakeDescribeCursor = cursor
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> Any:
        self.executed_sql.append(sql)
        return self._cursor

    def cursor(self) -> Any:
        return self._cursor


class FakeSnowflakeMetadataCursor:
    """Cursor double exposing Snowflake-style metadata rows."""

    def __init__(self, row: tuple[object, ...] | None) -> None:
        self.row: tuple[object, ...] | None = row
        self.executed_sql: str | None = None
        self.executed_params: tuple[object, ...] | None = None
        self.closed: bool = False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed_sql = sql
        self.executed_params = params

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeMetadataConnection:
    """Connection double returning a preconfigured metadata cursor."""

    def __init__(self, cursor: FakeSnowflakeMetadataCursor) -> None:
        self._cursor: FakeSnowflakeMetadataCursor = cursor

    def cursor(self) -> FakeSnowflakeMetadataCursor:
        return self._cursor
