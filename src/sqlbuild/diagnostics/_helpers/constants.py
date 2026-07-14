"""Diagnostics constants."""

from __future__ import annotations

LOGGER_ROOT_NAME: str = "sqlbuild"
LOG_FILE_NAME: str = "sqlbuild.log"
FILE_LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
SQL_SEPARATOR: str = "-" * 80
INLINE_SQL_TRANSACTION_STATEMENTS: tuple[str, ...] = ("BEGIN", "COMMIT", "ROLLBACK")
