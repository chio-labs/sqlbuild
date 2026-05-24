"""Helpers for MotherDuck adapter unit tests."""

from __future__ import annotations

from typing import Any


class FakeDuckDbConnection:
    """Connection double recording DuckDB SQL execution."""

    def __init__(self) -> None:
        self.executed_sql: list[str] = []

    def execute(self, sql: str) -> FakeDuckDbConnection:
        self.executed_sql.append(sql)
        return self


class FakeDuckDbModule:
    """Module double for duckdb.connect."""

    def __init__(self) -> None:
        self.connected_databases: list[str] = []
        self.connection: FakeDuckDbConnection = FakeDuckDbConnection()

    def connect(self, *, database: str) -> FakeDuckDbConnection:
        self.connected_databases.append(database)
        return self.connection


def install_fake_duckdb_module(monkeypatch: Any) -> FakeDuckDbModule:
    """Install a fake duckdb module for adapter connection tests."""

    import sys

    fake_module: FakeDuckDbModule = FakeDuckDbModule()
    monkeypatch.setitem(sys.modules, "duckdb", fake_module)
    return fake_module
