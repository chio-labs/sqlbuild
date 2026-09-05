"""Audit identity helper functions."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.auditing.models import AuditIdentity, MeasurementThresholdBound
from sqlbuild.compiler.auditing.types import AuditEvaluationMode, ThresholdOperator
from sqlbuild.compiler.fingerprints.main._normalize_query_sql import normalize_query_sql
from sqlbuild.compiler.planner.models import AuditPlanEntry


def audit_identity(audit: AuditPlanEntry) -> AuditIdentity:
    """Build identity values for one planned audit binding."""

    payload: dict[str, object] = {
        "audit_name": audit.name,
        "attachment_kind": audit.attachment_kind.value,
        "attached_target_name": audit.attached_target_name,
        "attached_column_name": audit.attached_column_name,
        "severity": audit.severity.value,
        "run_scope_phase": audit.effective_run_scope.value,
        "always_run": audit.always_run,
    }
    if audit.evaluation_mode == AuditEvaluationMode.MEASUREMENT:
        payload.update(
            {
                "evaluation_mode": audit.evaluation_mode.value,
                "value_column": audit.value_column,
                "sample_count_column": audit.sample_count_column,
                "sample_unit": audit.sample_unit,
                "thresholds": _normalized_thresholds(audit),
                "minimum_samples": audit.minimum_samples,
            }
        )
    definition_payload: dict[str, object] = {
        **payload,
        "unresolved_sql": normalize_query_sql(audit.unresolved_sql),
    }
    execution_identity_payload: dict[str, object] = {
        **payload,
        "resolved_sql": normalize_query_sql(audit.resolved_sql),
    }
    if audit.evaluation_mode == AuditEvaluationMode.MEASUREMENT:
        definition_payload["evidence_unresolved_sql"] = _normalized_optional_sql(
            audit.evidence_unresolved_sql
        )
        execution_identity_payload["evidence_resolved_sql"] = _normalized_optional_sql(
            audit.evidence_resolved_sql
        )
    return AuditIdentity(
        binding_key=hash_payload(payload),
        audit_name=audit.name,
        definition_fingerprint=hash_payload(definition_payload),
        execution_fingerprint=hash_payload(execution_identity_payload),
        severity=audit.severity,
        run_scope_phase=audit.effective_run_scope.value,
        attachment_kind=audit.attachment_kind.value,
        attached_target_name=audit.attached_target_name,
        attached_column_name=audit.attached_column_name,
        always_run=audit.always_run,
    )


def binding_payload(audit: AuditIdentity) -> dict[str, object]:
    """Return the target-neutral binding payload for one audit identity."""

    return {
        "binding_key": audit.binding_key,
        "audit_name": audit.audit_name,
        "severity": audit.severity.value,
        "run_scope_phase": audit.run_scope_phase,
        "attachment_kind": audit.attachment_kind,
        "attached_target_name": audit.attached_target_name,
        "attached_column_name": audit.attached_column_name,
        "always_run": audit.always_run,
    }


def execution_payload(audit: AuditIdentity) -> dict[str, object]:
    """Return the execution payload for one audit identity."""

    return {
        **binding_payload(audit),
        "definition_fingerprint": audit.definition_fingerprint,
        "execution_fingerprint": audit.execution_fingerprint,
    }


def hash_payload(payload: object) -> str:
    """Hash a JSON-serializable identity payload."""

    encoded: str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _normalized_thresholds(audit: AuditPlanEntry) -> dict[str, object] | None:
    if audit.thresholds is None:
        return None
    return {
        "warn": _normalized_bound(audit.thresholds.warn),
        "error": _normalized_bound(audit.thresholds.error),
    }


def _normalized_bound(bound: MeasurementThresholdBound | None) -> dict[str, object] | None:
    if bound is None:
        return None
    operator: ThresholdOperator = bound.operator
    if operator == ThresholdOperator.OUTSIDE:
        return {
            "operator": operator.value,
            "lower": bound.lower,
            "upper": bound.upper,
        }
    return {"operator": operator.value, "limit": bound.limit}


def _normalized_optional_sql(sql: str | None) -> str | None:
    return None if sql is None else normalize_query_sql(sql)
