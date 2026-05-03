"""Connection lifecycle mixin for adapter implementations."""

from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable
from typing import Any


class ConnectionMixin:
    """Manages adapter connection lifecycle and transaction control."""

    @abstractmethod
    def connect(self, config: dict[str, Any]) -> Any:
        """Open and return a connection using the provided configuration."""
        ...

    @abstractmethod
    def execute(self, connection: Any, sql: str) -> Any:
        """Execute a SQL statement and return the result."""
        ...

    @abstractmethod
    def close(self, connection: Any) -> None:
        """Close the given connection."""
        ...

    def begin(self, connection: Any) -> None:
        """Begin a transaction."""
        self.execute(connection, "BEGIN")

    def commit(self, connection: Any) -> None:
        """Commit the current transaction."""
        self.execute(connection, "COMMIT")

    def rollback(self, connection: Any) -> None:
        """Roll back the current transaction."""
        self.execute(connection, "ROLLBACK")

    def run_in_transaction(self, connection: Any, fn: Callable[[], Any]) -> Any:
        """Execute fn inside a begin/commit/rollback boundary."""
        self.begin(connection)
        try:
            result: Any = fn()
            self.commit(connection)
        except BaseException:
            self.rollback(connection)
            raise
        return result

    def supports_transactions(self) -> bool:
        """Return whether this adapter supports explicit transactions."""
        return True
