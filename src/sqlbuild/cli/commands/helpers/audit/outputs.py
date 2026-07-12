"""Audit command output writing and exit-code phases."""

from __future__ import annotations

from sqlbuild.cli.commands.helpers.audit.models import AuditCommandRequest, AuditInvocation
from sqlbuild.cli.output.main.audit_execution_json import format_audit_execution_json
from sqlbuild.cli.output.main.write_execution_json_output import write_execution_json_output
from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.presentation.main.summary_footer import format_summary_footer


def write_audit_completion_output(
    *,
    request: AuditCommandRequest,
    invocation: AuditInvocation,
    results: tuple[AuditExecutionResult, ...],
) -> None:
    """Write the audit summary footer and optional JSON output."""

    pass_count: int = sum(1 for r in results if r.outcome == AuditOutcome.PASS)
    warn_count: int = sum(1 for r in results if r.outcome == AuditOutcome.WARN)
    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    invocation.progress_stream.write(
        "\n"
        + format_summary_footer(
            counts=(
                ("PASS", pass_count),
                ("WARN", warn_count),
                ("FAIL", fail_count),
                ("TOTAL", len(results)),
            ),
            use_color=invocation.use_color,
        )
        + "\n"
    )
    invocation.progress_stream.flush()
    write_execution_json_output(
        payload=format_audit_execution_json(results=results),
        json_output=request.json_output,
        json_output_path=request.json_output_path,
    )


def resolve_audit_exit_code(results: tuple[AuditExecutionResult, ...]) -> int:
    """Resolve the audit exit code from failed audit outcomes."""

    fail_count: int = sum(1 for r in results if r.outcome == AuditOutcome.ERROR)
    return 0 if fail_count == 0 else 1
