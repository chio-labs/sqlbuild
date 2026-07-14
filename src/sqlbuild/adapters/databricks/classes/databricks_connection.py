"""Databricks connection wrapper."""

from typing import Any


class _DatabricksConnection:
    """Small wrapper exposing a generic execute method for adapter helpers."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: Any = self.raw_connection.cursor()
        return cursor.execute(sql)

    def close(self) -> None:
        self.raw_connection.close()

    def cursor(self) -> Any:
        return self.raw_connection.cursor()
