"""Diagnostics file formatter."""

from __future__ import annotations

import logging

from sqlbuild.diagnostics._helpers.logging_formatters import (
    _append_exception,
    _format_prefix,
    _get_record_sql,
)

_FILE_LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"
_SQL_SEPARATOR: str = "-" * 80


class DiagnosticsFileFormatter(logging.Formatter):
    """Format diagnostics records for target/sqlbuild.log."""

    def format(self, record: logging.LogRecord) -> str:
        prefix: str = _format_prefix(
            record=record, date_text=self.formatTime(record, _FILE_LOG_DATE_FORMAT)
        )
        sql: str | None = _get_record_sql(record)
        if sql is None:
            return _append_exception(record=record, rendered=f"{prefix} {record.getMessage()}")
        return _append_exception(
            record=record,
            rendered=(
                f"{prefix} {record.getMessage()}\n{_SQL_SEPARATOR}\n"
                f"{sql.rstrip()}\n{_SQL_SEPARATOR}"
            ),
        )
