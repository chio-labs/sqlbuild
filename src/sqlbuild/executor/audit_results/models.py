"""Immutable records persisted to native audit result history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.executor.audit_results._helpers.identity import (
    build_audit_result_id as build_audit_result_id,
)


@dataclass(frozen=True)
class AuditResultRecord:
    """One immutable audit result fact."""

    result_id: str
    schema_version: int
    occurred_at: datetime
    invocation_id: str
    run_id: str
    audit_name: str
    audit_definition_name: str
    binding_key: str
    definition_fingerprint: str
    execution_fingerprint: str
    evaluation_mode: str
    run_scope_phase: str
    attachment_kind: str
    attached_target_kind: str | None
    attached_target_name: str | None
    attached_column_name: str | None
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    severity: str
    outcome: str
    execution_error: str | None
    violation_count: int | None
    measured_value: float | None
    sample_count: int | None
    sample_unit: str | None
    minimum_samples: int | None
    thresholds_json: str | None
    evidence_json: str | None
    evidence_count: int | None
    evidence_truncated: bool | None
    evidence_error: str | None
    measurement_sql: str | None
    evidence_sql: str | None
    executed_sql: str | None
    sql_digest: str | None
    metadata_json: str | None
    reused: bool
    audit_description: str | None = None
