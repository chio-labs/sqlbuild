"""Audit outcomes for the progress rows of standalone audits."""

from __future__ import annotations

from sqlbuild._native import NativeProgressProjector, current_native_progress_projector
from sqlbuild.executor.auditing.models import AuditExecutionResult


def record_audit_progress_outcome(
    *, resource_attempt_id: str, result: AuditExecutionResult
) -> None:
    """Show the audit's outcome, such as WARN, on its terminal row in the active progress."""

    projector: NativeProgressProjector | None = current_native_progress_projector()
    if projector is not None:
        projector.record_audit_outcome(
            resource_attempt_id=resource_attempt_id, outcome=result.outcome.value
        )
