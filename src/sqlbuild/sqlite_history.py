"""Typed public SQLite execution history API."""

from sqlbuild.runtime.execution_history.classes.sqlite_execution_history import (
    SQLiteExecutionHistory as _SQLiteExecutionHistory,
)

__all__ = ("SQLiteExecutionHistory",)


class SQLiteExecutionHistory(_SQLiteExecutionHistory):
    """Supported project-local SQLite execution history backend."""
