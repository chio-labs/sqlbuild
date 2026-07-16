"""Public audit execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_protocol_v1 import (
    format_audit_execution_json as _format_audit_execution_json,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult


def format_audit_execution_json(*, results: tuple[AuditExecutionResult, ...]) -> str:
    """Format audit command execution results as JSON."""

    return _format_audit_execution_json(results=results)
