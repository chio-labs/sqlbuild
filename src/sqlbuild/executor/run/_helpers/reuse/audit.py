"""Runtime helpers for safe audit proof reuse."""

from __future__ import annotations

from sqlbuild.compiler.auditing.main.identity import build_audit_gate_identity
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditRunScope, AuditSeverity
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run._helpers.reuse.fingerprint_metadata import (
    reuse_from_audit_gate_reuse_decision,
)
from sqlbuild.executor.run.models import AuditGateReuseDecision


def audit_plan_binding_key(audit: AuditPlanEntry) -> str:
    """Return the binding key for one planned audit."""

    return build_audit_gate_identity(audits=(audit,)).audits[0].binding_key


def reused_final_audit_results_by_binding_key(
    *, metadata_json: str | None, model_audits: tuple[AuditPlanEntry, ...]
) -> dict[str, AuditExecutionResult]:
    """Build reused final PASS audit results from accepted reuse_from origin proof."""

    decision: AuditGateReuseDecision = reuse_from_audit_gate_reuse_decision(
        metadata_json=metadata_json,
        model_audits=model_audits,
    )
    if not decision.reusable:
        return {}
    reusable_binding_keys: frozenset[str] = frozenset(decision.reusable_binding_keys)
    results: dict[str, AuditExecutionResult] = {}
    audit: AuditPlanEntry
    for audit in model_audits:
        if audit.severity != AuditSeverity.ERROR:
            continue
        binding_key: str = audit_plan_binding_key(audit)
        if binding_key not in reusable_binding_keys:
            continue
        results[binding_key] = AuditExecutionResult(
            audit_name=audit.name,
            attachment_kind=audit.attachment_kind,
            severity=audit.severity,
            outcome=AuditOutcome.PASS,
            row_count=0,
            executed_sql=audit.resolved_sql,
            run_scope_phase=AuditRunScope.FINAL,
            attached_target_name=audit.attached_target_name,
            attached_column_name=audit.attached_column_name,
            reused=True,
        )
    return results
