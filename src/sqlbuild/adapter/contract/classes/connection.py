"""Connection lifecycle mixin for adapter implementations."""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any, ClassVar

from sqlbuild.adapter.contract.models import QueryResult
from sqlbuild.runtime.observability.classes.statement_lifecycle import StatementLifecycle


class ConnectionMixin(ABC):
    """Manages adapter connection lifecycle and transaction control."""

    adapter_name: ClassVar[str]

    @abstractmethod
    def connect(self, config: dict[str, Any]) -> Any:
        """Open and return a connection using the provided configuration."""
        ...

    def execute(self, *, connection: Any, sql: str) -> Any:
        """Execute SQL through the framework-owned statement lifecycle."""

        with StatementLifecycle(adapter=self.adapter_name, sql=sql, intent="execute") as lifecycle:
            result: Any = self._execute(connection=connection, sql=sql)
            lifecycle.completed(affected_rows=self.affected_row_count(cursor=result))
            return result

    @abstractmethod
    def _execute(self, *, connection: Any, sql: str) -> Any:
        """Execute one statement using the backend driver."""
        ...

    @abstractmethod
    def query(self, *, connection: Any, sql: str, limit: int | None) -> QueryResult:
        """Execute SQL and normalize row-returning results for CLI display."""
        ...

    def affected_row_count(self, *, cursor: Any) -> int | None:
        """Return the row count affected by the last DML statement, if known."""

        raw: object = getattr(cursor, "rowcount", None)
        if not isinstance(raw, int) or raw < 0:
            return None
        return raw

    @abstractmethod
    def close(self, connection: Any) -> None:
        """Close the given connection."""
        ...

    def begin(self, connection: Any) -> None:
        """Begin a transaction."""
        self.execute(connection=connection, sql="BEGIN")

    def commit(self, connection: Any) -> None:
        """Commit the current transaction."""
        self.execute(connection=connection, sql="COMMIT")

    def rollback(self, connection: Any) -> None:
        """Roll back the current transaction."""
        self.execute(connection=connection, sql="ROLLBACK")

    @contextlib.contextmanager
    def transaction(self, connection: Any) -> Generator[None]:
        """Context manager for a begin/commit/rollback boundary."""
        if not self.supports_transactions():
            yield
            return
        self.begin(connection)
        try:
            yield
            self.commit(connection)
        except BaseException:
            self.rollback(connection)
            raise

    def supports_transactions(self) -> bool:
        """Return whether this adapter supports explicit transactions."""
        return True
