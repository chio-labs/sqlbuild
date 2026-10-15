"""Typed public PostgreSQL execution history API."""

from sqlbuild._native import PostgresExecutionHistory as _NativePostgresExecutionHistory

__all__ = ("PostgresExecutionHistory",)


class PostgresExecutionHistory(_NativePostgresExecutionHistory):
    """Supported deployed PostgreSQL execution history backend."""
