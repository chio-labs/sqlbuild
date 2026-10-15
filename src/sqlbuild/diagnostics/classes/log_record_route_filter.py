"""Route-specific non-mutating diagnostic record filter."""

from __future__ import annotations

import logging

from sqlbuild._native import route_diagnostic_log_record


class LogRecordRouteFilter(logging.Filter):
    """Select a record family and return a redacted destination-specific copy."""

    def __init__(
        self,
        *,
        internal_only: bool,
        allow_internal: bool,
        include_sql_text: bool,
    ) -> None:
        super().__init__()
        self._internal_only: bool = internal_only
        self._allow_internal: bool = allow_internal
        self._include_sql_text: bool = include_sql_text

    def filter(self, record: logging.LogRecord) -> logging.LogRecord | bool:
        """Return a safe copy when the record belongs at this destination."""

        values: dict[str, object] | None = route_diagnostic_log_record(
            record=record,
            internal_only=self._internal_only,
            allow_internal=self._allow_internal,
            include_sql_text=self._include_sql_text,
        )
        if values is None:
            return False
        return logging.makeLogRecord(values)
