"""Helpers for Postgres adapter unit tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo


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
        return next(iter(self.rows), None)

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


def describe_equivalent_numeric_relation(
    connection: object, relation: str
) -> tuple[ColumnInfo, ...]:
    del connection
    columns_by_relation: dict[str, tuple[ColumnInfo, ...]] = {
        "left_relation": (ColumnInfo(name="total", type="NUMERIC(10,2)"),),
        "right_relation": (ColumnInfo(name="total", type="numeric(10,2)"),),
    }
    return columns_by_relation[relation]
