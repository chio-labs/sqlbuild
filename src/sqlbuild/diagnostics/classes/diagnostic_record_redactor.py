"""Public diagnostic record redaction boundary."""

from __future__ import annotations

import logging

from sqlbuild.diagnostics._helpers.redaction import redact_text, redact_value, safe_extra_fields


class DiagnosticRecordRedactor:
    """Expose secret-safe rendering to diagnostic destination handlers."""

    @staticmethod
    def text(value: str) -> str:
        """Redact obvious secrets from diagnostic text."""

        return redact_text(value)

    @staticmethod
    def value(*, name: str, value: object) -> object:
        """Redact one structured field value."""

        return redact_value(name=name, value=value)

    @staticmethod
    def extras(record: logging.LogRecord) -> dict[str, object]:
        """Collect redacted non-standard record fields."""

        return safe_extra_fields(record)
