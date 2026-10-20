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
        summarize_third_party: bool = False,
        project_roots: tuple[str, ...] = (),
    ) -> None:
        super().__init__()
        self._internal_only: bool = internal_only
        self._allow_internal: bool = allow_internal
        self._include_sql_text: bool = include_sql_text
        self._summarize_third_party: bool = summarize_third_party
        self._project_roots: tuple[str, ...] = project_roots

    def filter(self, record: logging.LogRecord) -> logging.LogRecord | bool:
        """Return a safe copy when the record belongs at this destination."""

        values: dict[str, object] | None = route_diagnostic_log_record(
            record=record,
            internal_only=self._internal_only,
            allow_internal=self._allow_internal,
            include_sql_text=self._include_sql_text,
            summarize_third_party=self._summarize_third_party,
            project_roots=self._project_roots,
        )
        if values is None:
            return False
        return logging.makeLogRecord(values)
