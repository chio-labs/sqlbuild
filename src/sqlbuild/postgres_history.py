"""Typed public PostgreSQL execution history API."""

from sqlbuild.runtime.execution_history.classes.postgres_execution_history import (
    PostgresExecutionHistory as _PostgresExecutionHistory,
)

__all__ = ("PostgresExecutionHistory",)


class PostgresExecutionHistory(_PostgresExecutionHistory):
    """Supported deployed PostgreSQL execution history backend."""
