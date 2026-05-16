"""Execution result construction helpers."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus
from sqlbuild.shared.helpers.coded_errors import error_code, error_help, error_message


def build_failed_result(
    *,
    entry: ModelPlanEntry,
    phase: ExecutionPhase,
    error: str | BaseException,
    staging_relation: str | None = None,
    promoted_relation: str | None = None,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
) -> ModelExecutionResult:
    """Build a failed ModelExecutionResult for a specific phase."""

    rendered_error, rendered_code, rendered_help = _render_failure_error(error)

    statement_recorder.log(f"model {entry.name} failed phase={phase.value} error={rendered_error}")
    if staging_relation is not None:
        statement_recorder.log(f"staging relation kept for inspection: {staging_relation}")

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.FAILED,
        failed_phase=phase,
        staging_relation=staging_relation,
        promoted_relation=promoted_relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        error_code=rendered_code,
        error_help=rendered_help,
        error_message=rendered_error,
    )


def _render_failure_error(error: str | BaseException) -> tuple[str, str | None, str | None]:
    """Render legacy string failures and structured exceptions consistently."""

    if isinstance(error, str):
        return error, None, None
    return error_message(error), error_code(error, fallback_code="X000"), error_help(error)
