"""Measurement audit integration-envelope round-trip coverage."""

from __future__ import annotations

import pytest

from sqlbuild.cli.output._helpers.integration_result import build_integration_result
from sqlbuild.cli.output.models import IntegrationCheckResult, IntegrationResultEnvelope
from sqlbuild.compiler.auditing.models import (
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
from sqlbuild.executor.auditing.models import AuditExecutionResult
from sqlbuild.runtime.observability.models import LifecycleEvent
from tests.integration.src.sqlbuild.cli.output._test_types import MeasurementEnvelopeTestCase
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
    test_case: MeasurementEnvelopeTestCase,
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

    envelope: IntegrationResultEnvelope | None = build_integration_result(
        result=result,
        terminal=terminal,
        event_sequence=2,
        plan=None,
        command="audit",
    )

    assert envelope is not None
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
