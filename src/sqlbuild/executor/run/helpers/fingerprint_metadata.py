"""Model fingerprint metadata helpers."""

from __future__ import annotations

import json
from typing import cast

from sqlbuild.compiler.auditing.main.identity import build_audit_gate_identity
from sqlbuild.compiler.auditing.models import AuditGateIdentity, AuditIdentity
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditSeverity
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.models import AuditGateReuseDecision
from sqlbuild.executor.run.types import AuditGateMode, AuditGateReuseReason, AuditGateStatus


def model_fingerprint_metadata_with_audit_gate(
    *,
    metadata_json: str | None,
    model_audits: tuple[AuditPlanEntry, ...] = (),
    audit_results: tuple[AuditExecutionResult, ...] = (),
    run_id: str,
) -> str:
    """Return model fingerprint metadata JSON with compact audit gate proof."""

    if not model_audits:
        return metadata_json or "{}"
    metadata: dict[str, object] = json.loads(metadata_json or "{}")
    identity: AuditGateIdentity = build_audit_gate_identity(audits=model_audits)
    result_payloads: tuple[dict[str, object], ...] = tuple(
        sorted(
            _audit_result_payloads(identity=identity, audit_results=audit_results),
            key=lambda payload: (
                str(payload["binding_key"]),
                str(payload["run_scope_phase"]),
            ),
        )
    )
    metadata["audit_gate"] = {
        "status": _audit_gate_status(identity=identity, audit_results=audit_results),
        "binding_set_hash": identity.binding_set_hash,
        "blocking_set_hash": identity.blocking_set_hash,
        "mode": AuditGateMode.EXECUTED.value,
        "run_id": run_id,
        "results": result_payloads,
    }
    return json.dumps(metadata, sort_keys=True, separators=(",", ":"), default=str)


def same_target_audit_gate_reuse_decision(
    *, metadata_json: str | None, model_audits: tuple[AuditPlanEntry, ...]
) -> AuditGateReuseDecision:
    """Return whether prior same-target audit gate proof covers planned audits."""

    if not model_audits:
        return AuditGateReuseDecision(
            reusable=True,
            reason=AuditGateReuseReason.REUSABLE,
        )
    if any(audit.always_run for audit in model_audits):
        return AuditGateReuseDecision(
            reusable=False,
            reason=AuditGateReuseReason.ALWAYS_RUN,
        )
    audit_gate: dict[str, object] | None = _read_audit_gate(metadata_json)
    if audit_gate is None:
        return AuditGateReuseDecision(reusable=False, reason=AuditGateReuseReason.MISSING)
    status: object = audit_gate.get("status")
    if status != AuditGateStatus.PASSED.value:
        return AuditGateReuseDecision(reusable=False, reason=AuditGateReuseReason.NON_PASSING)
    identity: AuditGateIdentity = build_audit_gate_identity(audits=model_audits)
    if audit_gate.get("binding_set_hash") != identity.binding_set_hash:
        return AuditGateReuseDecision(
            reusable=False,
            reason=AuditGateReuseReason.BINDING_SET_CHANGED,
            missing_binding_keys=tuple(audit.binding_key for audit in identity.audits),
        )
    prior_results: dict[str, dict[str, object]] | None = _audit_gate_results_by_binding_key(
        audit_gate.get("results")
    )
    if prior_results is None:
        return AuditGateReuseDecision(reusable=False, reason=AuditGateReuseReason.MALFORMED)

    reusable_binding_keys: list[str] = []
    missing_binding_keys: list[str] = []
    audit: AuditIdentity
    for audit in identity.audits:
        prior_result: dict[str, object] | None = prior_results.get(audit.binding_key)
        if (
            prior_result is None
            or prior_result.get("execution_fingerprint") != audit.execution_fingerprint
        ):
            missing_binding_keys.append(audit.binding_key)
            continue
        reusable_binding_keys.append(audit.binding_key)
    if missing_binding_keys:
        return AuditGateReuseDecision(
            reusable=False,
            reason=AuditGateReuseReason.AUDIT_CHANGED,
            reusable_binding_keys=tuple(reusable_binding_keys),
            missing_binding_keys=tuple(missing_binding_keys),
        )
    return AuditGateReuseDecision(
        reusable=True,
        reason=AuditGateReuseReason.REUSABLE,
        reusable_binding_keys=tuple(reusable_binding_keys),
    )


def _read_audit_gate(metadata_json: str | None) -> dict[str, object] | None:
    if metadata_json is None:
        return None
    try:
        metadata: object = json.loads(metadata_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(metadata, dict):
        return None
    audit_gate: object = metadata.get("audit_gate")
    if not isinstance(audit_gate, dict):
        return None
    return audit_gate


def _audit_gate_results_by_binding_key(
    raw_results: object,
) -> dict[str, dict[str, object]] | None:
    if not isinstance(raw_results, list | tuple):
        return None
    results: dict[str, dict[str, object]] = {}
    raw_result: object
    for raw_result in raw_results:
        if not isinstance(raw_result, dict):
            return None
        result_payload: dict[str, object] = cast("dict[str, object]", raw_result)
        binding_key: object = result_payload.get("binding_key")
        if not isinstance(binding_key, str):
            return None
        results[binding_key] = result_payload
    return results


def _audit_result_payloads(
    *, identity: AuditGateIdentity, audit_results: tuple[AuditExecutionResult, ...]
) -> tuple[dict[str, object], ...]:
    payloads: list[dict[str, object]] = []
    result: AuditExecutionResult
    for result in audit_results:
        audit_identity: AuditIdentity | None = _find_audit_identity(
            identity=identity,
            result=result,
        )
        if audit_identity is None:
            continue
        payloads.append(
            {
                "binding_key": audit_identity.binding_key,
                "audit_name": result.audit_name,
                "definition_fingerprint": audit_identity.definition_fingerprint,
                "execution_fingerprint": audit_identity.execution_fingerprint,
                "severity": result.severity.value,
                "run_scope_phase": result.run_scope_phase.value,
                "outcome": result.outcome.value,
                "row_count": result.row_count,
                "attached_target_name": result.attached_target_name,
                "attached_column_name": result.attached_column_name,
                "always_run": audit_identity.always_run,
            }
        )
    return tuple(payloads)


def _audit_gate_status(
    *, identity: AuditGateIdentity, audit_results: tuple[AuditExecutionResult, ...]
) -> str:
    if not audit_results:
        return AuditGateStatus.INCOMPLETE.value
    if any(result.outcome == AuditOutcome.ERROR for result in audit_results):
        return AuditGateStatus.FAILED.value
    error_audits: tuple[AuditIdentity, ...] = tuple(
        audit for audit in identity.audits if audit.severity == AuditSeverity.ERROR.value
    )
    audit: AuditIdentity
    for audit in error_audits:
        if not any(
            _result_matches_identity(result=result, audit_identity=audit)
            for result in audit_results
        ):
            return AuditGateStatus.INCOMPLETE.value
    return AuditGateStatus.PASSED.value


def _find_audit_identity(
    *, identity: AuditGateIdentity, result: AuditExecutionResult
) -> AuditIdentity | None:
    audit_identity: AuditIdentity
    for audit_identity in identity.audits:
        if _result_matches_identity(result=result, audit_identity=audit_identity):
            return audit_identity
    return None


def _result_matches_identity(
    *, result: AuditExecutionResult, audit_identity: AuditIdentity
) -> bool:
    return (
        result.audit_name == audit_identity.audit_name
        and result.severity.value == audit_identity.severity
        and result.attachment_kind.value == audit_identity.attachment_kind
        and result.attached_target_name == audit_identity.attached_target_name
        and result.attached_column_name == audit_identity.attached_column_name
    )
