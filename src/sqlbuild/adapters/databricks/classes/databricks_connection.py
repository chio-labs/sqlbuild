"""Databricks connection wrapper."""

from typing import Any

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor


class _DatabricksConnection:
    """Small wrapper exposing a generic execute method for adapter helpers."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: ObservedCursor = self.cursor()
        return cursor.execute(sql)

    def close(self) -> None:
        self.raw_connection.close()

    def cursor(self) -> ObservedCursor:
        return ObservedCursor(raw_cursor=self.raw_connection.cursor(), adapter="databricks")
