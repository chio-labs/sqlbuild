"""Audit command output writing and exit-code phases."""

from __future__ import annotations

import json

from sqlbuild.cli.commands.models import AuditCommandRequest, AuditInvocation
from sqlbuild.cli.output.main._audit_execution_json import format_audit_execution_json
from sqlbuild.cli.output.main._write_execution_json_output import write_execution_json_output
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.executor.auditing.main.current_audit_result_projection import (
    current_audit_result_projection,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult, AuditResultProjection
from sqlbuild.presentation.main.summary_footer import format_summary_footer


def write_audit_completion_output(
    *,
    request: AuditCommandRequest,
    invocation: AuditInvocation,
    results: tuple[AuditExecutionResult, ...],
    configured_concurrency: int,
    worker_count: int,
) -> None:
    """Write the audit summary footer and optional JSON output."""

    pass_count: int = sum(1 for r in results if r.outcome == AuditOutcome.PASS)
    warn_count: int = sum(1 for r in results if r.outcome == AuditOutcome.WARN)
    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    insufficient_count: int = sum(
        1 for r in results if r.outcome == AuditOutcome.INSUFFICIENT
    )
    invocation.progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("WARN", warn_count),
                ("FAIL", fail_count),
                ("INSUFFICIENT", insufficient_count),
                ("TOTAL", len(results)),
            ),
            use_color=invocation.use_color,
        )
        + "\n"
    )
    invocation.progress_stream.flush()
    payload: str = format_audit_execution_json(
            results=results,
            configured_concurrency=configured_concurrency,
            worker_count=worker_count,
        )
    projection: AuditResultProjection | None = current_audit_result_projection()
    if projection is not None:
        document: dict[str, object] = json.loads(payload)
        document["audit_result_projection"] = {
            "attempted_count": projection.attempted_count,
            "written_count": projection.written_count,
            "failed_count": projection.failed_count,
        }
        if projection.degraded:
            document["projection_degraded"] = True
            document["projection_degradation_reasons"] = [
                {
                    "reason": "audit_result_persistence_failure",
                    "attempted_count": projection.attempted_count,
                    "written_count": projection.written_count,
                    "failed_count": projection.failed_count,
                }
            ]
        payload = json.dumps(document, indent=2) + "\n"
    write_execution_json_output(
        payload=payload,
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_audit_exit_code(results: tuple[AuditExecutionResult, ...]) -> int:
    """Resolve the audit exit code from failed audit outcomes."""

    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    return 0 if fail_count == 0 else 1
