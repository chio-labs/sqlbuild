"""Model fingerprint metadata helpers."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import cast

from sqlbuild.compiler.auditing.main.identity import build_audit_gate_identity
from sqlbuild.compiler.auditing.models import AuditGateIdentity, AuditIdentity
from sqlbuild.compiler.auditing.types import AuditOutcome, AuditSeverity
from sqlbuild.compiler.fingerprints.constants import AUDIT_GATE_METADATA_KEY
from sqlbuild.compiler.planner.models import AuditPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.models import (
    AuditGateMetadata,
    AuditGateMetadataParseFailureDetail,
    AuditGateResultMetadata,
    AuditGateReuseDecision,
)
from sqlbuild.executor.run.types import (
    AuditGateMetadataParseFailure,
    AuditGateMode,
    AuditGateReuseReason,
    AuditGateStatus,
)

_LOGGER: logging.Logger = logging.getLogger("sqlbuild.execution")

_STATUS_KEY: str = "status"
_BINDING_SET_HASH_KEY: str = "binding_set_hash"
_BLOCKING_SET_HASH_KEY: str = "blocking_set_hash"
_MODE_KEY: str = "mode"
_RUN_ID_KEY: str = "run_id"
_RESULTS_KEY: str = "results"
_BINDING_KEY: str = "binding_key"
_AUDIT_NAME_KEY: str = "audit_name"
_DEFINITION_FINGERPRINT_KEY: str = "definition_fingerprint"
_EXECUTION_FINGERPRINT_KEY: str = "execution_fingerprint"
_SEVERITY_KEY: str = "severity"
_RUN_SCOPE_PHASE_KEY: str = "run_scope_phase"
_OUTCOME_KEY: str = "outcome"
_ROW_COUNT_KEY: str = "row_count"
_ATTACHED_TARGET_NAME_KEY: str = "attached_target_name"
_ATTACHED_COLUMN_NAME_KEY: str = "attached_column_name"
_ALWAYS_RUN_KEY: str = "always_run"
_REUSED_KEY: str = "reused"


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
    result_payloads: tuple[AuditGateResultMetadata, ...] = tuple(
        sorted(
            _audit_result_payloads(identity=identity, audit_results=audit_results),
            key=lambda payload: (
                payload.binding_key,
                str(payload.fields[_RUN_SCOPE_PHASE_KEY]),
            ),
        )
    )
    audit_gate: AuditGateMetadata = AuditGateMetadata(
        status=_audit_gate_status(identity=identity, audit_results=audit_results),
        binding_set_hash=identity.binding_set_hash,
        results=result_payloads,
        fields={
            _BLOCKING_SET_HASH_KEY: identity.blocking_set_hash,
            _MODE_KEY: AuditGateMode.EXECUTED.value,
            _RUN_ID_KEY: run_id,
        },
    )
    metadata[AUDIT_GATE_METADATA_KEY] = render_audit_gate_metadata(audit_gate)
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
    audit_gate: AuditGateMetadata | AuditGateMetadataParseFailureDetail = _read_audit_gate(
        metadata_json
    )
    if isinstance(audit_gate, AuditGateMetadataParseFailureDetail):
        _log_parse_failure(audit_gate)
        return AuditGateReuseDecision(
            reusable=False, reason=_parse_failure_reuse_reason(audit_gate)
        )
    if audit_gate.status != AuditGateStatus.PASSED.value:
        return AuditGateReuseDecision(reusable=False, reason=AuditGateReuseReason.NON_PASSING)
    identity: AuditGateIdentity = build_audit_gate_identity(audits=model_audits)
    if audit_gate.binding_set_hash != identity.binding_set_hash:
        return AuditGateReuseDecision(
            reusable=False,
            reason=AuditGateReuseReason.BINDING_SET_CHANGED,
            missing_binding_keys=tuple(audit.binding_key for audit in identity.audits),
        )
    prior_results: dict[str, AuditGateResultMetadata] = {
        result.binding_key: result for result in audit_gate.results
    }

    reusable_binding_keys: list[str] = []
    missing_binding_keys: list[str] = []
    audit: AuditIdentity
    for audit in identity.audits:
        prior_result: AuditGateResultMetadata | None = prior_results.get(audit.binding_key)
        if (
            prior_result is None
            or prior_result.execution_fingerprint != audit.execution_fingerprint
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


def reuse_from_audit_gate_reuse_decision(
    *, metadata_json: str | None, model_audits: tuple[AuditPlanEntry, ...]
) -> AuditGateReuseDecision:
    """Return whether reuse_from origin proof covers current blocking audits."""

    blocking_audits: tuple[AuditPlanEntry, ...] = tuple(
        audit for audit in model_audits if audit.severity == AuditSeverity.ERROR
    )
    if not blocking_audits:
        return AuditGateReuseDecision(reusable=True, reason=AuditGateReuseReason.REUSABLE)
    if any(audit.always_run for audit in blocking_audits):
        return AuditGateReuseDecision(reusable=False, reason=AuditGateReuseReason.ALWAYS_RUN)
    audit_gate: AuditGateMetadata | AuditGateMetadataParseFailureDetail = _read_audit_gate(
        metadata_json
    )
    if isinstance(audit_gate, AuditGateMetadataParseFailureDetail):
        _log_parse_failure(audit_gate)
        return AuditGateReuseDecision(
            reusable=False, reason=_parse_failure_reuse_reason(audit_gate)
        )
    if audit_gate.status != AuditGateStatus.PASSED.value:
        return AuditGateReuseDecision(reusable=False, reason=AuditGateReuseReason.NON_PASSING)

    identity: AuditGateIdentity = build_audit_gate_identity(audits=blocking_audits)
    prior_results: dict[str, AuditGateResultMetadata] = {
        result.binding_key: result for result in audit_gate.results
    }

    reusable_binding_keys: list[str] = []
    missing_binding_keys: list[str] = []
    audit: AuditIdentity
    for audit in identity.audits:
        prior_result: AuditGateResultMetadata | None = prior_results.get(audit.binding_key)
        if (
            prior_result is None
            or prior_result.definition_fingerprint != audit.definition_fingerprint
            or prior_result.outcome != AuditOutcome.PASS.value
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


def parse_audit_gate_metadata(
    metadata_json: str | Mapping[str, object] | None,
) -> AuditGateMetadata | AuditGateMetadataParseFailureDetail:
    """Parse model fingerprint JSON into a typed audit-gate payload."""

    if metadata_json is None:
        return _parse_error(
            reason=AuditGateMetadataParseFailure.MISSING_FIELD,
            detail=AUDIT_GATE_METADATA_KEY,
        )
    if isinstance(metadata_json, str):
        try:
            metadata: object = json.loads(metadata_json)
        except json.JSONDecodeError as error:
            return _parse_error(
                reason=AuditGateMetadataParseFailure.CORRUPT_JSON,
                detail=str(error),
            )
    else:
        metadata = metadata_json
    if not isinstance(metadata, dict):
        return _parse_error(reason=AuditGateMetadataParseFailure.NON_DICT, detail="metadata")
    if AUDIT_GATE_METADATA_KEY not in metadata:
        return _parse_error(
            reason=AuditGateMetadataParseFailure.MISSING_FIELD,
            detail=AUDIT_GATE_METADATA_KEY,
        )
    audit_gate: object = metadata[AUDIT_GATE_METADATA_KEY]
    if not isinstance(audit_gate, dict):
        return _parse_error(
            reason=AuditGateMetadataParseFailure.WRONG_TYPE,
            detail=AUDIT_GATE_METADATA_KEY,
        )
    audit_gate_payload: dict[str, object] = cast("dict[str, object]", audit_gate)
    required_gate_fields: tuple[str, ...] = (
        _STATUS_KEY,
        _BINDING_SET_HASH_KEY,
        _RESULTS_KEY,
    )
    field_name: str
    for field_name in required_gate_fields:
        if field_name not in audit_gate_payload:
            return _parse_error(
                reason=AuditGateMetadataParseFailure.MISSING_FIELD,
                detail=f"{AUDIT_GATE_METADATA_KEY}.{field_name}",
            )
    status: object = audit_gate_payload[_STATUS_KEY]
    binding_set_hash: object = audit_gate_payload[_BINDING_SET_HASH_KEY]
    raw_results: object = audit_gate_payload[_RESULTS_KEY]
    if not isinstance(status, str):
        return _parse_error(reason=AuditGateMetadataParseFailure.WRONG_TYPE, detail=_STATUS_KEY)
    if not isinstance(binding_set_hash, str):
        return _parse_error(
            reason=AuditGateMetadataParseFailure.WRONG_TYPE,
            detail=_BINDING_SET_HASH_KEY,
        )
    if not isinstance(raw_results, list | tuple):
        return _parse_error(reason=AuditGateMetadataParseFailure.WRONG_TYPE, detail=_RESULTS_KEY)
    results: list[AuditGateResultMetadata] = []
    raw_result: object
    for index, raw_result in enumerate(raw_results):
        if not isinstance(raw_result, dict):
            return _parse_error(
                reason=AuditGateMetadataParseFailure.WRONG_TYPE,
                detail=f"{_RESULTS_KEY}[{index}]",
            )
        required_result_fields: tuple[str, ...] = (
            _BINDING_KEY,
            _DEFINITION_FINGERPRINT_KEY,
            _EXECUTION_FINGERPRINT_KEY,
            _OUTCOME_KEY,
        )
        for field_name in required_result_fields:
            if field_name not in raw_result:
                return _parse_error(
                    reason=AuditGateMetadataParseFailure.MISSING_FIELD,
                    detail=f"{_RESULTS_KEY}[{index}].{field_name}",
                )
            if not isinstance(raw_result[field_name], str):
                return _parse_error(
                    reason=AuditGateMetadataParseFailure.WRONG_TYPE,
                    detail=f"{_RESULTS_KEY}[{index}].{field_name}",
                )
        results.append(
            AuditGateResultMetadata(
                binding_key=raw_result[_BINDING_KEY],
                definition_fingerprint=raw_result[_DEFINITION_FINGERPRINT_KEY],
                execution_fingerprint=raw_result[_EXECUTION_FINGERPRINT_KEY],
                outcome=raw_result[_OUTCOME_KEY],
                fields={
                    key: value
                    for key, value in raw_result.items()
                    if key not in required_result_fields
                },
            )
        )
    return AuditGateMetadata(
        status=status,
        binding_set_hash=binding_set_hash,
        results=tuple(results),
        fields={
            key: value
            for key, value in audit_gate_payload.items()
            if key not in required_gate_fields
        },
    )


def render_audit_gate_metadata(payload: AuditGateMetadata) -> dict[str, object]:
    """Render a typed audit-gate payload without changing its persisted shape."""

    rendered_results: list[dict[str, object]] = []
    for result in payload.results:
        rendered_result: dict[str, object] = dict(result.fields)
        rendered_result.update(
            {
                _BINDING_KEY: result.binding_key,
                _DEFINITION_FINGERPRINT_KEY: result.definition_fingerprint,
                _EXECUTION_FINGERPRINT_KEY: result.execution_fingerprint,
                _OUTCOME_KEY: result.outcome,
            }
        )
        rendered_results.append(rendered_result)
    rendered: dict[str, object] = dict(payload.fields)
    rendered.update(
        {
            _STATUS_KEY: payload.status,
            _BINDING_SET_HASH_KEY: payload.binding_set_hash,
            _RESULTS_KEY: rendered_results,
        }
    )
    return rendered


def _read_audit_gate(
    metadata_json: str | None,
) -> AuditGateMetadata | AuditGateMetadataParseFailureDetail:
    return parse_audit_gate_metadata(metadata_json)


def _parse_error(
    *, reason: AuditGateMetadataParseFailure, detail: str
) -> AuditGateMetadataParseFailureDetail:
    return AuditGateMetadataParseFailureDetail(reason=reason, detail=detail)


def _log_parse_failure(error: AuditGateMetadataParseFailureDetail) -> None:
    _LOGGER.debug(
        "Audit gate reuse denied because metadata parsing failed: %s (%s)",
        error.reason.value,
        error.detail,
    )


def _parse_failure_reuse_reason(
    error: AuditGateMetadataParseFailureDetail,
) -> AuditGateReuseReason:
    if (
        error.reason
        in {
            AuditGateMetadataParseFailure.CORRUPT_JSON,
            AuditGateMetadataParseFailure.NON_DICT,
        }
        or error.detail == AUDIT_GATE_METADATA_KEY
    ):
        return AuditGateReuseReason.MISSING
    return AuditGateReuseReason.MALFORMED


def _audit_result_payloads(
    *, identity: AuditGateIdentity, audit_results: tuple[AuditExecutionResult, ...]
) -> tuple[AuditGateResultMetadata, ...]:
    payloads: list[AuditGateResultMetadata] = []
    result: AuditExecutionResult
    for result in audit_results:
        audit_identity: AuditIdentity | None = _find_audit_identity(
            identity=identity,
            result=result,
        )
        if audit_identity is None:
            continue
        payloads.append(
            AuditGateResultMetadata(
                binding_key=audit_identity.binding_key,
                definition_fingerprint=audit_identity.definition_fingerprint,
                execution_fingerprint=audit_identity.execution_fingerprint,
                outcome=result.outcome.value,
                fields={
                    _AUDIT_NAME_KEY: result.audit_name,
                    _SEVERITY_KEY: result.severity.value,
                    _RUN_SCOPE_PHASE_KEY: result.run_scope_phase.value,
                    _ROW_COUNT_KEY: result.row_count,
                    _ATTACHED_TARGET_NAME_KEY: result.attached_target_name,
                    _ATTACHED_COLUMN_NAME_KEY: result.attached_column_name,
                    _ALWAYS_RUN_KEY: audit_identity.always_run,
                    _REUSED_KEY: result.reused,
                },
            )
        )
    return tuple(payloads)


def _audit_gate_status(
    *, identity: AuditGateIdentity, audit_results: tuple[AuditExecutionResult, ...]
) -> str:
    """Pass when every error audit executed without ERROR; insufficient stays non-blocking."""

    if not audit_results:
        return AuditGateStatus.INCOMPLETE.value
    if any(result.outcome == AuditOutcome.ERROR for result in audit_results):
        return AuditGateStatus.FAILED.value
    error_audits: tuple[AuditIdentity, ...] = tuple(
        audit for audit in identity.audits if audit.severity == AuditSeverity.ERROR
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
        and result.severity == audit_identity.severity
        and result.attachment_kind.value == audit_identity.attachment_kind
        and result.attached_target_name == audit_identity.attached_target_name
        and result.attached_column_name == audit_identity.attached_column_name
    )
