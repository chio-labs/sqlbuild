"""Typed public SQLite execution history API."""

from sqlbuild._native import SQLiteExecutionHistory as _NativeSQLiteExecutionHistory

__all__ = ("SQLiteExecutionHistory",)


class SQLiteExecutionHistory(_NativeSQLiteExecutionHistory):
    """Supported project-local SQLite execution history backend."""
