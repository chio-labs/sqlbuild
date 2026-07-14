"""SQL Server connection wrapper."""

from typing import Any


class _SqlServerConnection:
    """Thin wrapper exposing a cursor-based execute interface over pymssql."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection

    def execute(self, sql: str) -> Any:
        cursor: Any = self.raw_connection.cursor()
        cursor.execute(sql)
        return cursor

    def cursor(self) -> Any:
        return self.raw_connection.cursor()

    def close(self) -> None:
        self.raw_connection.close()
