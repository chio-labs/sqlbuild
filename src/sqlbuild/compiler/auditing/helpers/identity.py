"""Audit identity helper functions."""

from __future__ import annotations

import hashlib
import json

from sqlbuild.compiler.auditing.models import AuditIdentity
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.shared.helpers.hashing import normalize_query_sql


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
    definition_payload: dict[str, object] = {
        **payload,
        "unresolved_sql": normalize_query_sql(audit.unresolved_sql),
    }
    execution_identity_payload: dict[str, object] = {
        **payload,
        "resolved_sql": normalize_query_sql(audit.resolved_sql),
    }
    return AuditIdentity(
        binding_key=hash_payload(payload),
        audit_name=audit.name,
        definition_fingerprint=hash_payload(definition_payload),
        execution_fingerprint=hash_payload(execution_identity_payload),
        severity=audit.severity.value,
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
        "severity": audit.severity,
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
