"""Diagnostic log JSON encode entrypoint."""

from sqlbuild.runtime.observability._helpers.observability import (
    diagnostic_log_to_json as _diagnostic_log_to_json,
)
from sqlbuild.runtime.observability.models import DiagnosticLog


def diagnostic_log_to_json(log: DiagnosticLog) -> str:
    """Serialize a structured diagnostic log deterministically."""

    return _diagnostic_log_to_json(log)
