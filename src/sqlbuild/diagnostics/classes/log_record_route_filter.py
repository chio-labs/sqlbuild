"""Route-specific non-mutating diagnostic record filter."""

from __future__ import annotations

import logging

from sqlbuild.diagnostics.classes.diagnostic_record_redactor import DiagnosticRecordRedactor
from sqlbuild.diagnostics.constants import (
    LOGGER_PREFIX,
    LOGGER_ROOT_NAME,
    REDACTED_SQL_LOG_MESSAGE,
    SQL_DIGEST_FIELD,
    SQL_TEXT_FIELD,
)


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

        internal: bool = record.name == LOGGER_ROOT_NAME or record.name.startswith(LOGGER_PREFIX)
        if self._internal_only and not internal:
            return False
        if internal and not self._allow_internal:
            return False
        if not internal and record.levelno < logging.INFO:
            return False
        if (
            self._include_sql_text
            and SQL_DIGEST_FIELD in record.__dict__
            and SQL_TEXT_FIELD not in record.__dict__
        ):
            return False
        copied_values: dict[str, object] = dict(record.__dict__)
        try:
            copied_values["msg"] = DiagnosticRecordRedactor.text(record.getMessage())
        except Exception:
            copied_values["msg"] = "<unformattable diagnostic message>"
        copied_values["args"] = ()
        if SQL_DIGEST_FIELD in copied_values:
            copied_values["msg"] = REDACTED_SQL_LOG_MESSAGE
        if record.exc_info is not None:
            try:
                exception_text: str = logging.Formatter().formatException(record.exc_info)
                copied_values["msg"] = (
                    f"{copied_values['msg']}\n{DiagnosticRecordRedactor.text(exception_text)}"
                )
            except Exception:
                pass
            copied_values["exc_info"] = None
            copied_values["exc_text"] = None
        for key, value in tuple(copied_values.items()):
            if key.startswith("sqlbuild_") and key != SQL_TEXT_FIELD:
                copied_values[key] = DiagnosticRecordRedactor.value(name=key, value=value)
        if not self._include_sql_text:
            copied_values.pop(SQL_TEXT_FIELD, None)
        return logging.makeLogRecord(copied_values)
