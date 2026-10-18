"""PostgreSQL connection wrapper."""

import math
from typing import Any

from sqlbuild.adapter.contract.classes.observed_cursor import ObservedCursor
from sqlbuild.adapters.postgres.constants import TRANSACTION_OPEN_STATUS
from sqlbuild.runtime.execution_limits.classes.item_deadline import ItemDeadline
from sqlbuild.runtime.execution_limits.main.current_execution_deadline import (
    current_execution_deadline,
)
from sqlbuild.runtime.execution_limits.models import ExecutionDeadline


class _PostgresConnection:
    """Thin wrapper exposing a cursor-based execute interface over a raw psycopg connection."""

    def __init__(self, raw_connection: Any) -> None:
        self.raw_connection: Any = raw_connection
        self._local_timeout_set: bool = False
        self._local_timeout_deadline: int | None = None
        self._sql_test_transaction: bool = False

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
        """Bound a statement in a transaction with SET LOCAL; never set it for a pooled session."""

        deadline: ExecutionDeadline | ItemDeadline | None = current_execution_deadline()
        if deadline is not None:
            deadline.enforce()
        if not self.in_transaction():
            self._local_timeout_set = False
            self._local_timeout_deadline = None
            return
        if deadline is None:
            if self._local_timeout_set:
                self.raw_connection.execute("SET LOCAL statement_timeout TO DEFAULT")
                self._local_timeout_set = False
                self._local_timeout_deadline = None
            return
        if self._local_timeout_set and self._local_timeout_deadline == id(deadline):
            return
        milliseconds: int = max(1, math.ceil(deadline.remaining_seconds * 1000))
        self.raw_connection.execute(f"SET LOCAL statement_timeout = {milliseconds}")
        self._local_timeout_set = True
        self._local_timeout_deadline = id(deadline)

    def needs_sql_test_transaction(self) -> bool:
        """Whether a unit test must open its own transaction before storing outputs."""

        return not self._sql_test_transaction and not self.in_transaction()

    def claim_sql_test_transaction(self) -> None:
        """Record that the transaction a unit test just opened is its own to end."""

        self._sql_test_transaction = True

    def release_sql_test_transaction(self) -> bool:
        """Whether a unit test owned the open transaction, which it must now end."""

        owned: bool = self._sql_test_transaction
        self._sql_test_transaction = False
        return owned

    def in_transaction(self) -> bool:
        """Whether a healthy transaction is open on the server session."""

        info: object = getattr(self.raw_connection, "info", None)
        status: object = getattr(info, "transaction_status", None)
        return getattr(status, "name", None) == TRANSACTION_OPEN_STATUS
