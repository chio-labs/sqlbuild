"""Audit execution result models."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)


@dataclass(frozen=True)
class AuditExecutionResult:
    """Outcome of one audit execution against a built relation."""

    audit_name: str
    attachment_kind: AuditAttachmentKind
    severity: AuditSeverity
    outcome: AuditOutcome
    row_count: int
    executed_sql: str
    run_scope_phase: AuditRunScope = AuditRunScope.FINAL
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    reused: bool = False
