"""Execution result construction helpers."""

from __future__ import annotations

from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.shared.types import ExecutionPhase, ExecutionStatus


def build_failed_result(
    *,
    entry: ModelPlanEntry,
    phase: ExecutionPhase,
    error: str,
    staging_relation: str | None = None,
    promoted_relation: str | None = None,
    warnings: list[str],
    audit_results: list[AuditExecutionResult],
    statement_recorder: StatementRecorder,
) -> ModelExecutionResult:
    """Build a failed ModelExecutionResult for a specific phase."""

    return ModelExecutionResult(
        model_name=entry.name,
        status=ExecutionStatus.FAILED,
        failed_phase=phase,
        staging_relation=staging_relation,
        promoted_relation=promoted_relation,
        audit_results=tuple(audit_results),
        warning_messages=tuple(warnings),
        lifecycle_events=statement_recorder.snapshot(),
        error_message=error,
    )
