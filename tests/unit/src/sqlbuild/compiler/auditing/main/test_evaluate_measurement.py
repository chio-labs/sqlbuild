from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.main.evaluate_measurement import evaluate_measurement
from sqlbuild.compiler.auditing.models import (
    MeasurementThresholdBound,
    MeasurementThresholds,
)
from sqlbuild.compiler.auditing.types import AuditOutcome, ThresholdOperator
from tests.unit.src.sqlbuild.compiler.auditing.main._test_types import (
    EvaluateMeasurementTestCase,
    InvalidMeasuredValueTestCase,
)

BELOW_WARN: MeasurementThresholdBound = MeasurementThresholdBound(
    operator=ThresholdOperator.BELOW, limit=100.0
)
ABOVE_WARN: MeasurementThresholdBound = MeasurementThresholdBound(
    operator=ThresholdOperator.ABOVE, limit=100.0
)
OUTSIDE_WARN: MeasurementThresholdBound = MeasurementThresholdBound(
    operator=ThresholdOperator.OUTSIDE, lower=10.0, upper=20.0
)

EVALUATION_CASES: tuple[EvaluateMeasurementTestCase, ...] = (
    EvaluateMeasurementTestCase(
        description="below_value_under_limit_warns",
        measured_value=99.0,
        thresholds=MeasurementThresholds(warn=BELOW_WARN),
        expected_outcome=AuditOutcome.WARN,
    ),
    EvaluateMeasurementTestCase(
        description="below_value_at_limit_passes",
        measured_value=100.0,
        thresholds=MeasurementThresholds(warn=BELOW_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="below_value_over_limit_passes",
        measured_value=101.0,
        thresholds=MeasurementThresholds(warn=BELOW_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="above_value_under_limit_passes",
        measured_value=99.0,
        thresholds=MeasurementThresholds(warn=ABOVE_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="above_value_at_limit_passes",
        measured_value=100.0,
        thresholds=MeasurementThresholds(warn=ABOVE_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="above_value_over_limit_warns",
        measured_value=101.0,
        thresholds=MeasurementThresholds(warn=ABOVE_WARN),
        expected_outcome=AuditOutcome.WARN,
    ),
    EvaluateMeasurementTestCase(
        description="outside_value_below_range_warns",
        measured_value=9.0,
        thresholds=MeasurementThresholds(warn=OUTSIDE_WARN),
        expected_outcome=AuditOutcome.WARN,
    ),
    EvaluateMeasurementTestCase(
        description="outside_value_at_lower_boundary_passes",
        measured_value=10.0,
        thresholds=MeasurementThresholds(warn=OUTSIDE_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="outside_value_inside_range_passes",
        measured_value=15.0,
        thresholds=MeasurementThresholds(warn=OUTSIDE_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="outside_value_at_upper_boundary_passes",
        measured_value=20.0,
        thresholds=MeasurementThresholds(warn=OUTSIDE_WARN),
        expected_outcome=AuditOutcome.PASS,
    ),
    EvaluateMeasurementTestCase(
        description="outside_value_above_range_warns",
        measured_value=21.0,
        thresholds=MeasurementThresholds(warn=OUTSIDE_WARN),
        expected_outcome=AuditOutcome.WARN,
    ),
    EvaluateMeasurementTestCase(
        description="error_violation_takes_precedence_over_warning",
        measured_value=89.0,
        thresholds=MeasurementThresholds(
            warn=BELOW_WARN,
            error=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=90.0),
        ),
        expected_outcome=AuditOutcome.ERROR,
    ),
    EvaluateMeasurementTestCase(
        description="missing_sample_count_is_insufficient_before_error",
        measured_value=89.0,
        sample_count=None,
        minimum_samples=10,
        thresholds=MeasurementThresholds(
            warn=BELOW_WARN,
            error=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=90.0),
        ),
        expected_outcome=AuditOutcome.INSUFFICIENT,
    ),
    EvaluateMeasurementTestCase(
        description="low_sample_count_is_insufficient_before_error",
        measured_value=89.0,
        sample_count=9,
        minimum_samples=10,
        thresholds=MeasurementThresholds(
            warn=BELOW_WARN,
            error=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=90.0),
        ),
        expected_outcome=AuditOutcome.INSUFFICIENT,
    ),
    EvaluateMeasurementTestCase(
        description="minimum_sample_boundary_allows_evaluation",
        measured_value=89.0,
        sample_count=10,
        minimum_samples=10,
        thresholds=MeasurementThresholds(
            warn=BELOW_WARN,
            error=MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=90.0),
        ),
        expected_outcome=AuditOutcome.ERROR,
    ),
)

INVALID_VALUE_CASES: tuple[InvalidMeasuredValueTestCase, ...] = (
    InvalidMeasuredValueTestCase(
        description="nan", measured_value=float("nan"), expected_error_message="must be finite"
    ),
    InvalidMeasuredValueTestCase(
        description="positive_infinity",
        measured_value=float("inf"),
        expected_error_message="must be finite",
    ),
    InvalidMeasuredValueTestCase(
        description="negative_infinity",
        measured_value=float("-inf"),
        expected_error_message="must be finite",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        EvaluateMeasurementTestCase(
            description=case.description,
            measured_value=case.measured_value,
            thresholds=case.thresholds,
            expected_outcome=case.expected_outcome,
            sample_count=case.sample_count,
            minimum_samples=case.minimum_samples,
        )
        for case in EVALUATION_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_measurement_policy_when_evaluating_then_returns_expected_outcome(
    test_case: EvaluateMeasurementTestCase,
) -> None:
    result: AuditOutcome = evaluate_measurement(
        measured_value=test_case.measured_value,
        sample_count=test_case.sample_count,
        minimum_samples=test_case.minimum_samples,
        thresholds=test_case.thresholds,
    )

    assert result == test_case.expected_outcome


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidMeasuredValueTestCase(
            description=case.description,
            measured_value=case.measured_value,
            expected_error_message=case.expected_error_message,
        )
        for case in INVALID_VALUE_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_non_finite_value_when_evaluating_then_raises_clear_error(
    test_case: InvalidMeasuredValueTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_message):
        evaluate_measurement(
            measured_value=test_case.measured_value,
            sample_count=None,
            minimum_samples=None,
            thresholds=MeasurementThresholds(warn=BELOW_WARN),
        )
