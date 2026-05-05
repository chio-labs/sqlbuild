"""Helpers for Snowflake adapter unit tests."""

from __future__ import annotations

from typing import Any


class FakeSnowflakeDescribeCursor:
    """Cursor double exposing Snowflake-style description metadata."""

    def __init__(self, description: tuple[tuple[str], ...]) -> None:
        self.description: tuple[tuple[str], ...] = description
        self.executed_sql: str | None = None
        self.closed: bool = False

    def execute(self, sql: str) -> None:
        self.executed_sql = sql

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeDescribeConnection:
    """Connection double returning a preconfigured describe cursor."""

    def __init__(self, cursor: FakeSnowflakeDescribeCursor) -> None:
        self._cursor: FakeSnowflakeDescribeCursor = cursor

    def cursor(self) -> Any:
        return self._cursor
