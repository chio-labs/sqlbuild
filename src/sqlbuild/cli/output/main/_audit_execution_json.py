"""Public audit execution JSON formatting entrypoint."""

from __future__ import annotations

from sqlbuild.cli.output._helpers.execution_result_document import (
    format_audit_execution_json as _format_audit_execution_json,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult


def format_audit_execution_json(
    *,
    results: tuple[AuditExecutionResult, ...],
    configured_concurrency: int = 1,
    worker_count: int | None = None,
) -> str:
    """Format audit command execution results as JSON."""

    return _format_audit_execution_json(
        results=results,
        configured_concurrency=configured_concurrency,
        worker_count=worker_count,
    )
