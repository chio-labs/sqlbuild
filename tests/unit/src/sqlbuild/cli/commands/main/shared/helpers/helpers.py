"""Test helpers for CLI shared helpers tests."""

from __future__ import annotations

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.executor.auditing.models import AuditExecutionResult


def build_audit_result(
    *,
    name: str,
    outcome: AuditOutcome,
    run_scope_phase: AuditRunScope = AuditRunScope.FINAL,
    row_count: int = 0,
    column_name: str | None = None,
    target_name: str | None = "test_model",
) -> AuditExecutionResult:
    return AuditExecutionResult(
        audit_name=name,
        attachment_kind=AuditAttachmentKind.MODEL,
        severity=AuditSeverity.ERROR,
        outcome=outcome,
        row_count=row_count,
        executed_sql="SELECT 1",
        run_scope_phase=run_scope_phase,
        attached_target_name=target_name,
        attached_column_name=column_name,
    )
