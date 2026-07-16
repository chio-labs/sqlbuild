"""Helpers for Snowflake adapter unit tests."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from sqlbuild.adapter.contract.models import ColumnInfo


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

    def __init__(
        self,
        row: tuple[object, ...] | None = None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.row: tuple[object, ...] | None = row
        self.rows: list[tuple[object, ...]] = rows or []
        self.executed_sql: str | None = None
        self.executed_params: tuple[object, ...] | None = None
        self.closed: bool = False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executed_sql = sql
        self.executed_params = params

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[object, ...]]:
        return self.rows

    def close(self) -> None:
        self.closed = True


class FakeSnowflakeMetadataConnection:
    """Connection double returning a preconfigured metadata cursor."""

    def __init__(self, cursor: FakeSnowflakeMetadataCursor) -> None:
        self._cursor: FakeSnowflakeMetadataCursor = cursor

    def cursor(self) -> FakeSnowflakeMetadataCursor:
        return self._cursor


def describe_equivalent_numeric_relation(
    connection: object, relation: str
) -> tuple[ColumnInfo, ...]:
    del connection
    columns_by_relation: dict[str, tuple[ColumnInfo, ...]] = {
        "left_relation": (ColumnInfo(name="id", type="NUMBER(38,0)"),),
        "right_relation": (ColumnInfo(name="id", type="DECIMAL(38,0)"),),
    }
    return columns_by_relation[relation]


class FakeSnowflakeRawConnection:
    """Raw connector connection double for connect() tests."""

    def cursor(self) -> Any:
        raise AssertionError("connect test should not execute SQL")

    def close(self) -> None:
        pass


def install_fake_snowflake_connector(monkeypatch: Any) -> dict[str, object]:
    """Install a fake optional snowflake.connector module and capture connect kwargs."""

    captured_kwargs: dict[str, object] = {}
    snowflake_module: ModuleType = ModuleType("snowflake")
    connector_module: ModuleType = ModuleType("snowflake.connector")

    def connect(**kwargs: object) -> FakeSnowflakeRawConnection:
        captured_kwargs.update(kwargs)
        return FakeSnowflakeRawConnection()

    connector_module.__dict__["connect"] = connect
    snowflake_module.__dict__["connector"] = connector_module
    monkeypatch.setitem(sys.modules, "snowflake", snowflake_module)
    monkeypatch.setitem(sys.modules, "snowflake.connector", connector_module)
    return captured_kwargs
