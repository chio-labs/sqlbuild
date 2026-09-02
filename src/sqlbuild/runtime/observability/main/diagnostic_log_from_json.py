"""Diagnostic log JSON decode entrypoint."""

from sqlbuild.runtime.observability._helpers.observability import (
    diagnostic_log_from_json as _diagnostic_log_from_json,
)
from sqlbuild.runtime.observability.models import DiagnosticLog


def diagnostic_log_from_json(raw_json: str) -> DiagnosticLog:
    """Decode and validate a structured diagnostic log."""

    return _diagnostic_log_from_json(raw_json)
