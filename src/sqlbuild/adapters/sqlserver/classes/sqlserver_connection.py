"""SQL Server connection wrapper."""

from typing import Any

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor


class _SqlServerConnection:
    """Thin wrapper exposing a cursor-based execute interface over pymssql."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: ObservedCursor = self.cursor()
        cursor.execute(sql)
        return cursor

    def cursor(self) -> ObservedCursor:
        return ObservedCursor(raw_cursor=self.raw_connection.cursor(), adapter="sqlserver")

    def close(self) -> None:
        self.raw_connection.close()
