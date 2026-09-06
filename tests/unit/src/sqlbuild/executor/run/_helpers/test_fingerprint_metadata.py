"""Tests for model fingerprint metadata helpers."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
from typing import Any

import pytest

from sqlbuild.compiler.auditing.types import AuditOutcome, AuditSeverity
from sqlbuild.compiler.fingerprints.constants import AUDIT_GATE_METADATA_KEY
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run._helpers.reuse import fingerprinting
from sqlbuild.executor.run._helpers.reuse.fingerprint_metadata import (
    model_fingerprint_metadata_with_audit_gate,
    parse_audit_gate_metadata,
    render_audit_gate_metadata,
    reuse_from_audit_gate_reuse_decision,
    same_target_audit_gate_reuse_decision,
)
from sqlbuild.executor.run.models import (
    AuditGateMetadata,
    AuditGateMetadataParseFailureDetail,
    AuditGateReuseDecision,
)
from sqlbuild.executor.run.types import AuditGateMode, AuditGateReuseReason, AuditGateStatus
from tests.unit.src.sqlbuild.executor.run._helpers._test_types import (
    AuditGateMetadataFailureTestCase,
    AuditGateMetadataSchemaTestCase,
    AuditGatePartialReuseDecisionTestCase,
    AuditGateReuseDecisionTestCase,
    FingerprintAuditGateEdgeTestCase,
    FingerprintAuditGateMetadataTestCase,
    FingerprintAuditGateNoAuditsTestCase,
    ReuseFromAuditGateDecisionTestCase,
    TryWriteFingerprintAuditGateTestCase,
)
from tests.unit.src.sqlbuild.executor.run._helpers.helpers import (
    FakeRelationReuseAdapter,
    build_fingerprint_audit_plan_entry,
    build_fingerprint_audit_plan_entry_with_options,
    build_fingerprint_audit_result,
    build_result_model_plan_entry,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintAuditGateMetadataTestCase(
            description="pass result writes reusable audit gate proof",
            audit_outcome="pass",
            expected_status=AuditGateStatus.PASSED,
            expected_result_count=1,
            expected_existing_field="kept",
        ),
        FingerprintAuditGateMetadataTestCase(
            description="error result writes failed audit gate proof",
            audit_outcome="error",
            expected_status=AuditGateStatus.FAILED,
            expected_result_count=1,
            expected_existing_field="kept",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_results_when_building_fingerprint_metadata_then_audit_gate_is_recorded(
    test_case: FingerprintAuditGateMetadataTestCase,
) -> None:
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry()
    audit_result: AuditExecutionResult = build_fingerprint_audit_result(
        outcome=test_case.audit_outcome
    )

    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json=json.dumps({"existing": test_case.expected_existing_field}),
        model_audits=(audit,),
        audit_results=(audit_result,),
        run_id="run_1",
    )
    metadata: dict[str, object] = json.loads(metadata_json)

    assert metadata["existing"] == test_case.expected_existing_field
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value
    assert audit_gate["status"] == test_case.expected_status.value
    assert audit_gate["mode"] == AuditGateMode.EXECUTED.value
    assert audit_gate["run_id"] == "run_1"
    assert len(audit_gate["results"]) == test_case.expected_result_count  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateMetadataSchemaTestCase(
            description="written payload retains the pinned warehouse format",
            expected_serialized=(
                '{"audit_gate":{"binding_set_hash":"e8caed68bb3c3bc0cb2fd33e9701a789afcc32e874272a0f381072f5ad35803c",'
                '"blocking_set_hash":"734928618c041e13429bbe80355dff2b0f72ab32421b9d413820553810a91554",'
                '"mode":"executed","results":[{"always_run":false,"attached_column_name":"order_id",'
                '"attached_target_name":"orders","audit_name":"not_null_orders",'
                '"binding_key":"ec8e86d82472ac0f5772d1c1a4ee1600dcec056474a1b7099f86840889fc15b2",'
                '"definition_fingerprint":"e9cd7c351d9602fc524c68d266d2d3d9daaccd52367591daafec675074b266c7",'
                '"execution_fingerprint":"f15c815cb150c3cd6bdc7b2edea5fcfcdd629b720e012eed819d4c9aa089f292",'
                '"outcome":"pass","reused":false,"row_count":0,"run_scope_phase":"final",'
                '"severity":"error"}],"run_id":"run_1","status":"passed"},"existing":"kept"}'
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_written_audit_gate_when_parsing_and_rendering_then_round_trips_pinned_format(
    test_case: AuditGateMetadataSchemaTestCase,
) -> None:
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json='{"existing":"kept"}',
        model_audits=(build_fingerprint_audit_plan_entry(),),
        audit_results=(build_fingerprint_audit_result(outcome="pass"),),
        run_id="run_1",
    )
    payload: AuditGateMetadata | AuditGateMetadataParseFailureDetail = parse_audit_gate_metadata(
        metadata_json
    )

    assert isinstance(payload, AuditGateMetadata)
    rendered_payload: dict[str, object] = render_audit_gate_metadata(payload)
    assert rendered_payload == json.loads(metadata_json)[AUDIT_GATE_METADATA_KEY]
    assert parse_audit_gate_metadata({AUDIT_GATE_METADATA_KEY: rendered_payload}) == payload
    assert metadata_json == test_case.expected_serialized


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateMetadataFailureTestCase(
            description="corrupt JSON is diagnosed",
            metadata_json="{",
            expected_diagnostic="corrupt JSON",
        ),
        AuditGateMetadataFailureTestCase(
            description="non-dict JSON is diagnosed",
            metadata_json="[]",
            expected_diagnostic="non-dict payload",
        ),
        AuditGateMetadataFailureTestCase(
            description="missing audit gate field is diagnosed",
            metadata_json="{}",
            expected_diagnostic="missing field",
        ),
        AuditGateMetadataFailureTestCase(
            description="wrong audit gate type is diagnosed",
            metadata_json='{"audit_gate":[]}',
            expected_diagnostic="wrong type",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_metadata_when_deciding_reuse_then_denies_with_debug_diagnostic(
    test_case: AuditGateMetadataFailureTestCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="sqlbuild.execution")

    decision: AuditGateReuseDecision = same_target_audit_gate_reuse_decision(
        metadata_json=test_case.metadata_json,
        model_audits=(build_fingerprint_audit_plan_entry(),),
    )

    assert decision.reusable is False
    assert test_case.expected_diagnostic in caplog.text


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintAuditGateNoAuditsTestCase(
            description="no model audits leaves metadata unchanged",
            expected_existing_field="kept",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_model_audits_when_building_fingerprint_metadata_then_metadata_is_unchanged(
    test_case: FingerprintAuditGateNoAuditsTestCase,
) -> None:
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json=json.dumps({"existing": test_case.expected_existing_field}),
        model_audits=(),
        audit_results=(),
        run_id="run_1",
    )
    metadata: dict[str, object] = json.loads(metadata_json)

    assert metadata["existing"] == test_case.expected_existing_field
    assert "audit_gate" not in metadata


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintAuditGateEdgeTestCase(
            description="warn-only result writes passed proof",
            plan_severity=AuditSeverity.WARN.value,
            result_outcome=AuditOutcome.WARN.value,
            result_audit_name="not_null_orders",
            result_column_name="order_id",
            expected_status=AuditGateStatus.PASSED,
            expected_result_count=1,
        ),
        FingerprintAuditGateEdgeTestCase(
            description="mismatched result writes incomplete proof",
            plan_severity=AuditSeverity.ERROR.value,
            result_outcome=AuditOutcome.PASS.value,
            result_audit_name="other_audit",
            result_column_name="order_id",
            expected_status=AuditGateStatus.INCOMPLETE,
            expected_result_count=0,
        ),
        FingerprintAuditGateEdgeTestCase(
            description="mismatched column writes incomplete proof",
            plan_severity=AuditSeverity.ERROR.value,
            result_outcome=AuditOutcome.PASS.value,
            result_audit_name="not_null_orders",
            result_column_name="other_column",
            expected_status=AuditGateStatus.INCOMPLETE,
            expected_result_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_edge_audit_results_when_building_fingerprint_metadata_then_status_is_conservative(
    test_case: FingerprintAuditGateEdgeTestCase,
) -> None:
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        severity=test_case.plan_severity
    )
    audit_results: tuple[AuditExecutionResult, ...] = (
        build_fingerprint_audit_result(
            outcome=test_case.result_outcome,
            audit_name=test_case.result_audit_name,
            severity=test_case.plan_severity,
            attached_column_name=test_case.result_column_name,
        ),
    )

    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=audit_results,
        run_id="run_1",
    )
    metadata: dict[str, object] = json.loads(metadata_json)
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value

    assert audit_gate["status"] == test_case.expected_status.value
    assert len(audit_gate["results"]) == test_case.expected_result_count  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateReuseDecisionTestCase(
            description="matching passed proof is reusable",
            metadata_mode="written",
            status=AuditGateStatus.PASSED,
            planned_attached_column_name="order_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
            expected_reusable=True,
            expected_reason=AuditGateReuseReason.REUSABLE,
            expected_reusable_count=1,
            expected_missing_count=0,
        ),
        AuditGateReuseDecisionTestCase(
            description="failed proof is not reusable",
            metadata_mode="written",
            status=AuditGateStatus.FAILED,
            planned_attached_column_name="order_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.NON_PASSING,
            expected_reusable_count=0,
            expected_missing_count=0,
        ),
        AuditGateReuseDecisionTestCase(
            description="binding set change is not reusable",
            metadata_mode="written",
            status=AuditGateStatus.PASSED,
            planned_attached_column_name="customer_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.BINDING_SET_CHANGED,
            expected_reusable_count=0,
            expected_missing_count=1,
        ),
        AuditGateReuseDecisionTestCase(
            description="same binding with changed execution SQL is not reusable",
            metadata_mode="written",
            status=AuditGateStatus.PASSED,
            planned_attached_column_name="order_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id < 0",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.AUDIT_CHANGED,
            expected_reusable_count=0,
            expected_missing_count=1,
        ),
        AuditGateReuseDecisionTestCase(
            description="always_run audit is not reusable",
            metadata_mode="written",
            status=AuditGateStatus.PASSED,
            planned_attached_column_name="order_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.ALWAYS_RUN,
            expected_reusable_count=0,
            expected_missing_count=0,
            planned_always_run=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_prior_audit_gate_when_deciding_same_target_reuse_then_returns_decision(
    test_case: AuditGateReuseDecisionTestCase,
) -> None:
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry()
    audit_result: AuditExecutionResult = build_fingerprint_audit_result(outcome="pass")
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=(audit_result,),
        run_id="run_1",
    )
    metadata: dict[str, object] = json.loads(metadata_json)
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value
    audit_gate["status"] = test_case.status.value
    metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))

    planned_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        attached_column_name=test_case.planned_attached_column_name,
        resolved_sql=test_case.planned_resolved_sql,
        always_run=test_case.planned_always_run,
    )

    decision: AuditGateReuseDecision = same_target_audit_gate_reuse_decision(
        metadata_json=metadata_json,
        model_audits=(planned_audit,),
    )

    assert decision.reusable is test_case.expected_reusable
    assert decision.reason == test_case.expected_reason
    assert len(decision.reusable_binding_keys) == test_case.expected_reusable_count
    assert len(decision.missing_binding_keys) == test_case.expected_missing_count


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateReuseDecisionTestCase(
            description="missing proof is not reusable",
            metadata_mode="missing",
            status=AuditGateStatus.PASSED,
            planned_attached_column_name="order_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.MISSING,
            expected_reusable_count=0,
            expected_missing_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_audit_gate_when_deciding_same_target_reuse_then_returns_missing(
    test_case: AuditGateReuseDecisionTestCase,
) -> None:
    planned_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        attached_column_name=test_case.planned_attached_column_name,
        resolved_sql=test_case.planned_resolved_sql,
    )

    decision: AuditGateReuseDecision = same_target_audit_gate_reuse_decision(
        metadata_json="{}",
        model_audits=(planned_audit,),
    )

    assert decision.reusable is test_case.expected_reusable
    assert decision.reason == test_case.expected_reason
    assert len(decision.reusable_binding_keys) == test_case.expected_reusable_count
    assert len(decision.missing_binding_keys) == test_case.expected_missing_count


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGateReuseDecisionTestCase(
            description="malformed results are not reusable",
            metadata_mode="malformed_results",
            status=AuditGateStatus.PASSED,
            planned_attached_column_name="order_id",
            planned_resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.MALFORMED,
            expected_reusable_count=0,
            expected_missing_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_audit_gate_when_deciding_same_target_reuse_then_returns_malformed(
    test_case: AuditGateReuseDecisionTestCase,
) -> None:
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry()
    audit_result: AuditExecutionResult = build_fingerprint_audit_result(outcome="pass")
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=(audit_result,),
        run_id="run_1",
    )
    metadata: dict[str, object] = json.loads(metadata_json)
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value
    audit_gate["results"] = {"not": "a list"}
    metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
    planned_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        attached_column_name=test_case.planned_attached_column_name,
        resolved_sql=test_case.planned_resolved_sql,
    )

    decision: AuditGateReuseDecision = same_target_audit_gate_reuse_decision(
        metadata_json=metadata_json,
        model_audits=(planned_audit,),
    )

    assert decision.reusable is test_case.expected_reusable
    assert decision.reason == test_case.expected_reason
    assert len(decision.reusable_binding_keys) == test_case.expected_reusable_count
    assert len(decision.missing_binding_keys) == test_case.expected_missing_count


@pytest.mark.parametrize(
    "test_case",
    [
        AuditGatePartialReuseDecisionTestCase(
            description="one changed audit reports reusable and missing binding keys",
            changed_resolved_sql="SELECT customer_id FROM analytics.orders WHERE customer_id < 0",
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.AUDIT_CHANGED,
            expected_reusable_count=1,
            expected_missing_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_one_changed_audit_when_deciding_same_target_reuse_then_returns_partial_keys(
    test_case: AuditGatePartialReuseDecisionTestCase,
) -> None:
    unchanged_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        name="not_null_orders",
        attached_column_name="order_id",
        resolved_sql="SELECT order_id FROM analytics.orders WHERE order_id IS NULL",
    )
    changed_prior_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        name="not_null_customers",
        attached_column_name="customer_id",
        resolved_sql="SELECT customer_id FROM analytics.orders WHERE customer_id IS NULL",
    )
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(unchanged_audit, changed_prior_audit),
        audit_results=(
            build_fingerprint_audit_result(
                outcome="pass",
                audit_name="not_null_orders",
                attached_column_name="order_id",
            ),
            build_fingerprint_audit_result(
                outcome="pass",
                audit_name="not_null_customers",
                attached_column_name="customer_id",
            ),
        ),
        run_id="run_1",
    )
    changed_current_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        name="not_null_customers",
        attached_column_name="customer_id",
        resolved_sql=test_case.changed_resolved_sql,
    )

    decision: AuditGateReuseDecision = same_target_audit_gate_reuse_decision(
        metadata_json=metadata_json,
        model_audits=(unchanged_audit, changed_current_audit),
    )

    assert decision.reusable is test_case.expected_reusable
    assert decision.reason == test_case.expected_reason
    assert len(decision.reusable_binding_keys) == test_case.expected_reusable_count
    assert len(decision.missing_binding_keys) == test_case.expected_missing_count


@pytest.mark.parametrize(
    "test_case",
    [
        ReuseFromAuditGateDecisionTestCase(
            description="prod dev resolved SQL difference keeps target-neutral proof reusable",
            origin_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            origin_resolved_sql="SELECT order_id FROM prod.orders WHERE order_id IS NULL",
            planned_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            planned_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            severity=AuditSeverity.ERROR.value,
            expected_reusable=True,
            expected_reason=AuditGateReuseReason.REUSABLE,
            expected_reusable_count=1,
            expected_missing_count=0,
        ),
        ReuseFromAuditGateDecisionTestCase(
            description="changed unresolved SQL rejects origin proof",
            origin_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            origin_resolved_sql="SELECT order_id FROM prod.orders WHERE order_id IS NULL",
            planned_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id < 0',
            planned_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id < 0",
            severity=AuditSeverity.ERROR.value,
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.AUDIT_CHANGED,
            expected_reusable_count=0,
            expected_missing_count=1,
        ),
        ReuseFromAuditGateDecisionTestCase(
            description="always_run rejects origin proof",
            origin_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            origin_resolved_sql="SELECT order_id FROM prod.orders WHERE order_id IS NULL",
            planned_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            planned_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            severity=AuditSeverity.ERROR.value,
            expected_reusable=False,
            expected_reason=AuditGateReuseReason.ALWAYS_RUN,
            expected_reusable_count=0,
            expected_missing_count=0,
            planned_always_run=True,
        ),
        ReuseFromAuditGateDecisionTestCase(
            description="warn-only audit requires no blocking proof",
            origin_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            origin_resolved_sql="SELECT order_id FROM prod.orders WHERE order_id IS NULL",
            planned_unresolved_sql='SELECT order_id FROM __ref("orders") WHERE order_id IS NULL',
            planned_resolved_sql="SELECT order_id FROM dev.orders WHERE order_id IS NULL",
            severity=AuditSeverity.WARN.value,
            expected_reusable=True,
            expected_reason=AuditGateReuseReason.REUSABLE,
            expected_reusable_count=0,
            expected_missing_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_origin_audit_gate_when_deciding_reuse_from_proof_then_uses_definition_identity(
    test_case: ReuseFromAuditGateDecisionTestCase,
) -> None:
    origin_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        name="not_null_orders",
        severity=test_case.severity,
        resolved_sql=test_case.origin_resolved_sql,
    )
    origin_audit = replace(origin_audit, unresolved_sql=test_case.origin_unresolved_sql)
    origin_result: AuditExecutionResult = build_fingerprint_audit_result(
        outcome="pass",
        audit_name="not_null_orders",
        severity=test_case.severity,
    )
    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(origin_audit,),
        audit_results=(origin_result,),
        run_id="prod_run",
    )
    planned_audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        name="not_null_orders",
        severity=test_case.severity,
        resolved_sql=test_case.planned_resolved_sql,
        always_run=test_case.planned_always_run,
    )
    planned_audit = replace(planned_audit, unresolved_sql=test_case.planned_unresolved_sql)

    decision: AuditGateReuseDecision = reuse_from_audit_gate_reuse_decision(
        metadata_json=metadata_json,
        model_audits=(planned_audit,),
    )

    assert decision.reusable is test_case.expected_reusable
    assert decision.reason == test_case.expected_reason
    assert len(decision.reusable_binding_keys) == test_case.expected_reusable_count
    assert len(decision.missing_binding_keys) == test_case.expected_missing_count


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintAuditGateEdgeTestCase(
            description="missing result writes incomplete proof",
            plan_severity=AuditSeverity.ERROR.value,
            result_outcome=AuditOutcome.PASS.value,
            result_audit_name="not_null_orders",
            result_column_name="order_id",
            expected_status=AuditGateStatus.INCOMPLETE,
            expected_result_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_missing_audit_result_when_building_fingerprint_metadata_then_status_is_incomplete(
    test_case: FingerprintAuditGateEdgeTestCase,
) -> None:
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        severity=test_case.plan_severity
    )

    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=(),
        run_id="run_1",
    )
    metadata: dict[str, object] = json.loads(metadata_json)
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value

    assert audit_gate["status"] == test_case.expected_status.value
    assert len(audit_gate["results"]) == test_case.expected_result_count  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "test_case",
    [
        FingerprintAuditGateEdgeTestCase(
            description="insufficient error audit is non-blocking",
            plan_severity=AuditSeverity.ERROR.value,
            result_outcome=AuditOutcome.INSUFFICIENT.value,
            result_audit_name="not_null_orders",
            result_column_name="order_id",
            expected_status=AuditGateStatus.PASSED,
            expected_result_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_executed_error_audit_with_insufficient_samples_when_building_gate_then_passes_gate_without_relabeling(
    test_case: FingerprintAuditGateEdgeTestCase,
) -> None:
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry_with_options(
        severity=test_case.plan_severity
    )
    result: AuditExecutionResult = build_fingerprint_audit_result(
        outcome=test_case.result_outcome,
        severity=test_case.plan_severity,
    )

    metadata_json: str = model_fingerprint_metadata_with_audit_gate(
        metadata_json="{}",
        model_audits=(audit,),
        audit_results=(result,),
        run_id="run_1",
    )

    audit_gate: dict[str, object] = json.loads(metadata_json)["audit_gate"]
    assert audit_gate["status"] == test_case.expected_status.value
    audit_results: list[dict[str, object]] = audit_gate["results"]  # type: ignore[assignment]
    assert audit_results[0]["outcome"] == test_case.result_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        TryWriteFingerprintAuditGateTestCase(
            description="fingerprint write receives audit gate metadata",
            expected_status=AuditGateStatus.PASSED,
            expected_result_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_audit_gate_when_writing_fingerprint_then_metadata_json_contains_audit_proof(
    test_case: TryWriteFingerprintAuditGateTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written_fingerprints: list[Fingerprint] = []

    def capture_fingerprint(**kwargs: Any) -> None:
        written_fingerprints.append(kwargs["fingerprint"])

    monkeypatch.setattr(fingerprinting, "write_fingerprint", capture_fingerprint)
    entry: ModelPlanEntry = build_result_model_plan_entry()
    audit: AuditPlanEntry = build_fingerprint_audit_plan_entry()
    audit_result: AuditExecutionResult = build_fingerprint_audit_result(outcome="pass")

    fingerprint_warnings: tuple[str, ...] = fingerprinting.try_write_fingerprint(
        entry=entry,
        adapter=FakeRelationReuseAdapter(supports_zero_copy_clone=True),
        connection=object(),
        run_id="run_1",
        query_change_tracking=True,
        model_audits=(audit,),
        audit_results=(audit_result,),
    )

    assert fingerprint_warnings == ()

    assert len(written_fingerprints) == 1
    metadata: dict[str, object] = json.loads(written_fingerprints[0].metadata_json)
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value
    assert audit_gate["status"] == test_case.expected_status.value
    assert len(audit_gate["results"]) == test_case.expected_result_count  # type: ignore[arg-type]
