"""SQL Server connection wrapper."""

import threading
from typing import Any

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.main.current_execution_deadline import (
    current_execution_deadline,
)
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


class _SqlServerConnection:
    """Thin wrapper exposing a cursor-based execute interface over pymssql."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection
        self._running: int = 0
        self._running_lock: threading.Lock = threading.Lock()

    def execute(self, sql: str) -> Any:
        deadline: ExecutionDeadline | ItemDeadline | None = current_execution_deadline()
        if deadline is not None:
            deadline.enforce()
        cursor: ObservedCursor = self.cursor()
        with self._running_lock:
            self._running += 1
        try:
            cursor.execute(sql)
        finally:
            with self._running_lock:
                self._running -= 1
        return cursor

    def cursor(self) -> ObservedCursor:
        return ObservedCursor(raw_cursor=self.raw_connection.cursor(), adapter="sqlserver")

    def cancel_active_statements(self) -> None:
        """Cancel the running statement through the driver's DB-Library cancel."""

        with self._running_lock:
            running: bool = self._running > 0
        if running:
            self.raw_connection._conn.cancel()

    def close(self) -> None:
        self.raw_connection.close()
