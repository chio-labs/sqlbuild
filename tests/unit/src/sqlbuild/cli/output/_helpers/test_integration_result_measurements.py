"""Measurement audit integration-result projection coverage."""

from __future__ import annotations

import pytest

from sqlbuild.cli.output._helpers.integration_result import _audit_result
from sqlbuild.cli.output.models import IntegrationCheckResult
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
from tests.unit.src.sqlbuild.cli.output._helpers._test_types import (
    MeasurementAuditOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        MeasurementAuditOutputTestCase("pass remains passing", AuditOutcome.PASS, "pass", True),
        MeasurementAuditOutputTestCase(
            "insufficient remains passing", AuditOutcome.INSUFFICIENT, "insufficient", True
        ),
        MeasurementAuditOutputTestCase("warn remains failing", AuditOutcome.WARN, "warn", False),
    ),
    ids=lambda case: case.description,
)
def test_given_measurement_outcome_when_projecting_then_status_and_passed_remain_distinct(
    test_case: MeasurementAuditOutputTestCase,
) -> None:
    result: AuditExecutionResult = AuditExecutionResult(
        audit_name="valid_rate",
        attachment_kind=AuditAttachmentKind.END,
        severity=AuditSeverity.WARN,
        outcome=test_case.outcome,
        row_count=0,
        executed_sql="SELECT 98.5 AS valid_rate",
        evaluation_mode=AuditEvaluationMode.MEASUREMENT,
    )

    check: IntegrationCheckResult = _audit_result(result)

    assert check.status == test_case.expected_status
    assert check.passed is test_case.expected_passed


@pytest.mark.parametrize(
    "test_case",
    (MeasurementAuditOutputTestCase("measurement summary", AuditOutcome.WARN, "warn", False),),
    ids=lambda case: case.description,
)
def test_given_measurement_audit_when_projecting_then_all_summary_fields_are_retained(
    test_case: MeasurementAuditOutputTestCase,
) -> None:
    result: AuditExecutionResult = AuditExecutionResult(
        audit_name="valid_rate",
        attachment_kind=AuditAttachmentKind.END,
        severity=AuditSeverity.WARN,
        outcome=test_case.outcome,
        row_count=0,
        executed_sql="SELECT 98.5 AS valid_rate",
        evaluation_mode=AuditEvaluationMode.MEASUREMENT,
        measured_value=98.5,
        sample_count=900,
        sample_unit="rows",
        minimum_samples=100,
        thresholds=MeasurementThresholds(
            warn=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=100.0),
            error=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=95.0),
        ),
        evidence_rows=({"id": 1}, {"id": 2}),
        evidence_truncated=True,
    )

    check: IntegrationCheckResult = _audit_result(result)

    assert check.status == test_case.expected_status
    assert check.evaluation_mode == "measurement"
    assert check.measured_value == 98.5
    assert check.sample_count == 900
    assert check.sample_unit == "rows"
    assert check.minimum_samples == 100
    assert check.thresholds == {
        "warn": {"operator": "below", "limit": 100.0},
        "error": {"operator": "below", "limit": 95.0},
    }
    assert check.evidence_count == 2
    assert check.evidence_truncated is True


@pytest.mark.parametrize(
    "test_case",
    (MeasurementAuditOutputTestCase("violations summary", AuditOutcome.PASS, "pass", True),),
    ids=lambda case: case.description,
)
def test_given_violations_audit_when_projecting_then_measurement_summary_is_absent(
    test_case: MeasurementAuditOutputTestCase,
) -> None:
    result: AuditExecutionResult = AuditExecutionResult(
        audit_name="not_null",
        attachment_kind=AuditAttachmentKind.END,
        severity=AuditSeverity.ERROR,
        outcome=test_case.outcome,
        row_count=0,
        executed_sql="SELECT 1 WHERE FALSE",
    )

    check: IntegrationCheckResult = _audit_result(result)

    assert check.status == test_case.expected_status
    assert check.evaluation_mode == "violations"
    assert check.measured_value is None
    assert check.sample_count is None
    assert check.sample_unit is None
    assert check.minimum_samples is None
    assert check.thresholds is None
    assert check.evidence_count is None
    assert check.evidence_truncated is None
