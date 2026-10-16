"""Public diagnostic record redaction boundary."""

from __future__ import annotations

import logging

from sqlbuild._native import (
    redact_diagnostic_text,
    redact_diagnostic_value,
    safe_diagnostic_extra_fields,
)


class DiagnosticRecordRedactor:
    """Expose secret-safe rendering to diagnostic destination handlers."""

    @staticmethod
    def text(value: str) -> str:
        """Redact obvious secrets from diagnostic text."""

        return redact_diagnostic_text(value)

    @staticmethod
    def value(*, name: str, value: object) -> object:
        """Redact one structured field value."""

        return redact_diagnostic_value(name=name, value=value)

    @staticmethod
    def extras(record: logging.LogRecord) -> dict[str, object]:
        """Collect redacted non-standard record fields."""

        return safe_diagnostic_extra_fields(record)
