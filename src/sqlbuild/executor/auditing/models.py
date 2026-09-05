"""Audit execution result models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlbuild.compiler.auditing.models import MeasurementThresholds
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditEvaluationMode,
    AuditOutcome,
    AuditRunScope,
    AuditSeverity,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind


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
    attached_target_kind: AttachedAuditTargetKind | None = None
    attached_target_name: str | None = None
    attached_column_name: str | None = None
    reused: bool = False
    evaluation_mode: AuditEvaluationMode = AuditEvaluationMode.VIOLATIONS
    measured_value: float | None = None
    sample_count: int | None = None
    sample_unit: str | None = None
    minimum_samples: int | None = None
    thresholds: MeasurementThresholds | None = None
    evidence_rows: tuple[Mapping[str, object], ...] = ()
    evidence_truncated: bool = False
    evidence_error: str | None = None
    evidence_sql: str | None = None
