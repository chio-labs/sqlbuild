"""Audit gate identity construction."""

from __future__ import annotations

from sqlbuild.compiler.auditing.helpers.identity import (
    audit_identity,
    binding_payload,
    execution_payload,
    hash_payload,
)
from sqlbuild.compiler.auditing.models import AuditGateIdentity, AuditIdentity
from sqlbuild.compiler.auditing.types import AuditSeverity
from sqlbuild.compiler.planner.models import AuditPlanEntry


def build_audit_gate_identity(*, audits: tuple[AuditPlanEntry, ...]) -> AuditGateIdentity:
    """Build target-neutral and target-specific identity hashes for planned audits."""

    audit_identities: tuple[AuditIdentity, ...] = tuple(
        sorted(
            (audit_identity(audit) for audit in audits), key=lambda identity: identity.binding_key
        )
    )
    binding_payloads: tuple[dict[str, object], ...] = tuple(
        binding_payload(audit) for audit in audit_identities
    )
    blocking_payloads: tuple[dict[str, object], ...] = tuple(
        execution_payload(audit)
        for audit in audit_identities
        if audit.severity == AuditSeverity.ERROR.value
    )
    return AuditGateIdentity(
        binding_set_hash=hash_payload(binding_payloads),
        blocking_set_hash=hash_payload(blocking_payloads),
        audits=audit_identities,
    )
