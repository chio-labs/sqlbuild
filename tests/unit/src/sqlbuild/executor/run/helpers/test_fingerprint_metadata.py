"""Tests for model fingerprint metadata helpers."""

from __future__ import annotations

import json
from typing import Any

import pytest

from sqlbuild.compiler.auditing.types import AuditOutcome, AuditSeverity
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import AuditPlanEntry, ModelPlanEntry
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.executor.run.helpers import fingerprinting
from sqlbuild.executor.run.helpers.fingerprint_metadata import (
    model_fingerprint_metadata_with_audit_gate,
)
from sqlbuild.executor.run.types import AuditGateMode, AuditGateStatus
from tests.unit.src.sqlbuild.executor.run.helpers._test_types import (
    FingerprintAuditGateEdgeTestCase,
    FingerprintAuditGateMetadataTestCase,
    FingerprintAuditGateNoAuditsTestCase,
    TryWriteFingerprintAuditGateTestCase,
)
from tests.unit.src.sqlbuild.executor.run.helpers.helpers import (
    FakeRelationReuseAdapter,
    build_fingerprint_audit_plan_entry,
    build_fingerprint_audit_plan_entry_with_options,
    build_fingerprint_audit_result,
    build_result_model_plan_entry,
)

FINGERPRINT_AUDIT_GATE_METADATA_TEST_CASES: list[FingerprintAuditGateMetadataTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    FINGERPRINT_AUDIT_GATE_METADATA_TEST_CASES,
    ids=[case.description for case in FINGERPRINT_AUDIT_GATE_METADATA_TEST_CASES],
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
        FingerprintAuditGateNoAuditsTestCase(
            description="no model audits leaves metadata unchanged",
            expected_existing_field="kept",
        )
    ],
    ids=["no model audits leaves metadata unchanged"],
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


FINGERPRINT_AUDIT_GATE_EDGE_TEST_CASES: list[FingerprintAuditGateEdgeTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    FINGERPRINT_AUDIT_GATE_EDGE_TEST_CASES,
    ids=[case.description for case in FINGERPRINT_AUDIT_GATE_EDGE_TEST_CASES],
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
    ids=["missing result writes incomplete proof"],
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
        TryWriteFingerprintAuditGateTestCase(
            description="fingerprint write receives audit gate metadata",
            expected_status=AuditGateStatus.PASSED,
            expected_result_count=1,
        )
    ],
    ids=["fingerprint write receives audit gate metadata"],
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

    fingerprinting.try_write_fingerprint(
        entry=entry,
        adapter=FakeRelationReuseAdapter(supports_zero_copy_clone=True),
        connection=object(),
        run_id="run_1",
        query_change_tracking=True,
        warnings=[],
        model_audits=(audit,),
        audit_results=(audit_result,),
    )

    assert len(written_fingerprints) == 1
    metadata: dict[str, object] = json.loads(written_fingerprints[0].metadata_json)
    audit_gate_value: object = metadata["audit_gate"]
    assert isinstance(audit_gate_value, dict)
    audit_gate: dict[str, object] = audit_gate_value
    assert audit_gate["status"] == test_case.expected_status.value
    assert len(audit_gate["results"]) == test_case.expected_result_count  # type: ignore[arg-type]
