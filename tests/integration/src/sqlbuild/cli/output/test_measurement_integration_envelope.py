"""Audit integration-envelope round-trip coverage."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild._native import (
    IntegrationCheckResult,
    IntegrationResultEnvelope,
    MeasurementThresholdBound,
    MeasurementThresholds,
)
from sqlbuild.compiler.auditing.types import (
    AuditAttachmentKind,
    AuditEvaluationMode,
    AuditOutcome,
    AuditSeverity,
    ThresholdOperator,
)
from sqlbuild.compiler.compile.types import AttachedAuditTargetKind
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.integration.src.sqlbuild.cli.output._test_types import (
    AttachmentKindEnvelopeTestCase,
    MeasurementEnvelopeTestCase,
)
from tests.unit.src.sqlbuild.cli.output._helpers.helpers import (
    audit_terminal,
    written_integration_record,
)
from tests.unit.src.sqlbuild.runtime.observability.helpers import lifecycle_event


@pytest.mark.parametrize(
    "test_case",
    (
        MeasurementEnvelopeTestCase(
            "insufficient measurement round trip",
            AuditOutcome.INSUFFICIENT,
            "insufficient",
            True,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_measurement_execution_result_when_building_envelope_then_decode_round_trip_is_complete(
    test_case: MeasurementEnvelopeTestCase, tmp_path: Path
) -> None:
    result: AuditExecutionResult = AuditExecutionResult(
        audit_name="valid_rate",
        audit_definition_name="test_audit",
        attachment_kind=AuditAttachmentKind.END,
        severity=AuditSeverity.WARN,
        outcome=test_case.outcome,
        row_count=0,
        executed_sql="SELECT 99.5 AS valid_rate",
        evaluation_mode=AuditEvaluationMode.MEASUREMENT,
        measured_value=99.5,
        sample_count=42,
        sample_unit="rows",
        minimum_samples=100,
        thresholds=MeasurementThresholds(
            warn=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=100.0)
        ),
    )
    terminal: LifecycleEvent = lifecycle_event(
        "resource_attempt_completed",
        run_id="run-1",
        resource_id="audit:valid_rate:end",
        resource_attempt_id="attempt-1",
        payload={
            "resource_kind": "audit",
            "resource_name": "valid_rate",
            "attempt_number": 1,
        },
    )

    envelope: IntegrationResultEnvelope = written_integration_record(
        result=result, terminal=terminal, directory=tmp_path, command="audit"
    )

    decoded: IntegrationResultEnvelope = IntegrationResultEnvelope.from_json(envelope.to_json())
    check: IntegrationCheckResult = decoded.checks[0]
    assert check.passed is test_case.expected_passed
    assert check.status == test_case.expected_status
    assert check.evaluation_mode == "measurement"
    assert check.measured_value == 99.5
    assert check.sample_count == 42
    assert check.sample_unit == "rows"
    assert check.minimum_samples == 100
    assert check.thresholds == {"warn": {"operator": "below", "limit": 100.0}}
    assert check.evidence_count == 0
    assert check.evidence_truncated is False


@pytest.mark.parametrize(
    "test_case",
    (
        AttachmentKindEnvelopeTestCase(
            "model audit",
            AuditAttachmentKind.MODEL,
            AttachedAuditTargetKind.MODEL,
            "orders",
            expected_attachment_kind="model",
            expected_asset_name="orders",
        ),
        AttachmentKindEnvelopeTestCase(
            "source audit",
            AuditAttachmentKind.SOURCE,
            AttachedAuditTargetKind.SOURCE,
            "raw_orders",
            expected_attachment_kind="source",
            expected_asset_name="raw_orders",
        ),
        AttachmentKindEnvelopeTestCase(
            "seed audit",
            AuditAttachmentKind.SEED,
            AttachedAuditTargetKind.SEED,
            "products",
            expected_attachment_kind="seed",
            expected_asset_name="products",
        ),
        AttachmentKindEnvelopeTestCase(
            "end-of-run audit",
            AuditAttachmentKind.END,
            None,
            None,
            expected_attachment_kind="end",
            expected_asset_name=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_every_attachment_kind_when_building_envelope_then_check_is_not_degraded(
    test_case: AttachmentKindEnvelopeTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result: AuditExecutionResult = AuditExecutionResult(
        audit_name="not_null",
        audit_definition_name="not_null",
        attachment_kind=test_case.attachment_kind,
        attached_target_kind=test_case.attached_target_kind,
        attached_target_name=test_case.attached_target_name,
        severity=AuditSeverity.ERROR,
        outcome=AuditOutcome.PASS,
        row_count=0,
        executed_sql="SELECT 1 WHERE FALSE",
    )

    envelope: IntegrationResultEnvelope = written_integration_record(
        result=result, terminal=audit_terminal(result), directory=tmp_path, command="audit"
    )

    check: IntegrationCheckResult = envelope.checks[0]
    assert envelope.projection_degraded is test_case.expected_degraded
    assert check.attachment_kind == test_case.expected_attachment_kind
    assert check.asset_name == test_case.expected_asset_name
    assert check.passed is test_case.expected_passed
    assert "integration output degraded" not in capsys.readouterr().err
