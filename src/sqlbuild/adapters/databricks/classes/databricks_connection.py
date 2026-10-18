"""Databricks connection wrapper."""

import math
import threading
from typing import Any

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.main.current_execution_deadline import (
    current_execution_deadline,
)
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline

_MAX_STATEMENT_TIMEOUT_SECONDS: int = 172_800


class _DatabricksConnection:
    """Small wrapper exposing a generic execute method for adapter helpers."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection
        self._statement_timeout_set: bool = False
        self._active_cursors: dict[int, Any] = {}
        self._cursors_lock: threading.Lock = threading.Lock()

    def execute(self, sql: str) -> Any:
        self._apply_statement_timeout()
        cursor: ObservedCursor = self.cursor()
        with self._cursors_lock:
            self._active_cursors[id(cursor.raw_cursor)] = cursor.raw_cursor
        try:
            return cursor.execute(sql)
        finally:
            with self._cursors_lock:
                self._active_cursors.pop(id(cursor.raw_cursor), None)

    def close(self) -> None:
        self.raw_connection.close()

    def cursor(self) -> ObservedCursor:
        return ObservedCursor(raw_cursor=self.raw_connection.cursor(), adapter="databricks")

    def cancel_active_statements(self) -> None:
        """Ask Databricks to cancel each statement this connection is running."""

        with self._cursors_lock:
            cursors: list[Any] = list(self._active_cursors.values())
        for raw_cursor in cursors:
            raw_cursor.cancel()

    def _apply_statement_timeout(self) -> None:
        """Bound the next statement by the remaining deadline, or restore the session default."""

        deadline: ExecutionDeadline | ItemDeadline | None = current_execution_deadline()
        if deadline is None:
            if self._statement_timeout_set:
                self._run_setting("RESET STATEMENT_TIMEOUT")
                self._statement_timeout_set = False
            return
        deadline.enforce()
        seconds: int = min(
            _MAX_STATEMENT_TIMEOUT_SECONDS, max(1, math.ceil(deadline.remaining_seconds))
        )
        self._run_setting(f"SET STATEMENT_TIMEOUT = {seconds}")
        self._statement_timeout_set = True

    def _run_setting(self, sql: str) -> None:
        raw_cursor: Any = self.raw_connection.cursor()
        try:
            raw_cursor.execute(sql)
        finally:
            raw_cursor.close()
