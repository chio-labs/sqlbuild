"""PostgreSQL connection wrapper."""

import math
from typing import Any

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.main.current_execution_deadline import (
    current_execution_deadline,
)
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


class _PostgresConnection:
    """Thin wrapper exposing a cursor-based execute interface over a raw psycopg connection."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection
        self._statement_timeout_set: bool = False

    def execute(self, sql: str) -> Any:
        self._apply_statement_timeout()
        cursor: ObservedCursor = self.cursor()
        cursor.execute(sql)
        return cursor

    def cursor(self) -> ObservedCursor:
        return ObservedCursor(raw_cursor=self.raw_connection.cursor(), adapter="postgres")

    def close(self) -> None:
        self.raw_connection.close()

    def _apply_statement_timeout(self) -> None:
        """Bound the next statement by the remaining deadline, or restore the session default."""

        deadline: ExecutionDeadline | ItemDeadline | None = current_execution_deadline()
        if deadline is None:
            if self._statement_timeout_set:
                self.raw_connection.execute("RESET statement_timeout")
                self._statement_timeout_set = False
            return
        deadline.enforce()
        milliseconds: int = max(1, math.ceil(deadline.remaining_seconds * 1000))
        self.raw_connection.execute(f"SET statement_timeout = {milliseconds}")
        self._statement_timeout_set = True
