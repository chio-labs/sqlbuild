"""The `recall.audit_evidence` setting the current invocation's audits collect evidence rows by."""

from __future__ import annotations

from contextvars import ContextVar

from sqlbuild.compiler.auditing.types import AuditOutcome
from sqlbuild.executor.auditing.constants import (
    AUDIT_EVIDENCE_ERROR_ONLY,
    AUDIT_EVIDENCE_OFF,
    DEFAULT_AUDIT_EVIDENCE,
)

current_audit_evidence: ContextVar[str] = ContextVar(
    "sqlbuild_audit_evidence", default=DEFAULT_AUDIT_EVIDENCE
)


def keeps_audit_evidence(*, outcome: AuditOutcome) -> bool:
    """Whether a failing audit with `outcome` collects the rows it flagged."""

    mode: str = current_audit_evidence.get()
    if mode == AUDIT_EVIDENCE_OFF:
        return False
    if mode == AUDIT_EVIDENCE_ERROR_ONLY:
        return outcome == AuditOutcome.ERROR
    return outcome in {AuditOutcome.WARN, AuditOutcome.ERROR}
