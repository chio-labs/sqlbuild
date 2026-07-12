"""Connection lifecycle mixin for adapter implementations."""

from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any

from sqlbuild.adapter.models import QueryResult


class ConnectionMixin(ABC):
    """Manages adapter connection lifecycle and transaction control."""

    @abstractmethod
    def connect(self, config: dict[str, Any]) -> Any:
        """Open and return a connection using the provided configuration."""
        ...

    @abstractmethod
    def execute(self, *, connection: Any, sql: str) -> Any:
        """Execute a SQL statement and return the result."""
        ...

    @abstractmethod
    def query(self, *, connection: Any, sql: str, limit: int | None) -> QueryResult:
        """Execute SQL and normalize row-returning results for CLI display."""
        ...

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
