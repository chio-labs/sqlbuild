"""Redacted structured fields of one logging record."""

from __future__ import annotations

import logging
from typing import Final

from sqlbuild._native import redact_diagnostic_value
from sqlbuild.diagnostics.constants import FORMATTER_RECORD_FIELDS, SQL_TEXT_FIELD

_STANDARD_RECORD_FIELDS: Final[frozenset[str]] = frozenset(logging.makeLogRecord({}).__dict__)


def safe_extra_fields(record: logging.LogRecord) -> dict[str, object]:
    """Collect redacted non-standard fields without evaluating arbitrary formatters."""

    return {
        key: redact_diagnostic_value(name=key, value=value)
        for key, value in record.__dict__.items()
        if key not in _STANDARD_RECORD_FIELDS
        and key not in FORMATTER_RECORD_FIELDS
        and key != SQL_TEXT_FIELD
    }
