from __future__ import annotations

import pytest

from sqlbuild.compiler.auditing.models import (
    MeasurementContract,
    MeasurementThresholdBound,
    MeasurementThresholds,
)
from sqlbuild.compiler.auditing.types import ThresholdOperator
from tests.unit.src.sqlbuild.compiler.auditing._test_types import (
    InvalidMeasurementContractTestCase,
    InvalidThresholdBoundTestCase,
    InvalidThresholdNestingTestCase,
    InvalidThresholdPolicyTestCase,
)
from tests.unit.src.sqlbuild.compiler.auditing.helpers import (
    build_measurement_threshold_bound,
)

INVALID_BOUND_CASES: tuple[InvalidThresholdBoundTestCase, ...] = (
    InvalidThresholdBoundTestCase(
        description="below_without_limit",
        operator=ThresholdOperator.BELOW,
        limit=None,
        lower=None,
        upper=None,
        expected_error_message="below threshold requires limit only",
    ),
    InvalidThresholdBoundTestCase(
        description="below_with_range_field",
        operator=ThresholdOperator.BELOW,
        limit=10.0,
        lower=0.0,
        upper=None,
        expected_error_message="below threshold requires limit only",
    ),
    InvalidThresholdBoundTestCase(
        description="above_with_range_field",
        operator=ThresholdOperator.ABOVE,
        limit=10.0,
        lower=None,
        upper=20.0,
        expected_error_message="above threshold requires limit only",
    ),
    InvalidThresholdBoundTestCase(
        description="outside_without_lower",
        operator=ThresholdOperator.OUTSIDE,
        limit=None,
        lower=None,
        upper=20.0,
        expected_error_message="outside threshold requires lower and upper only",
    ),
    InvalidThresholdBoundTestCase(
        description="outside_without_upper",
        operator=ThresholdOperator.OUTSIDE,
        limit=None,
        lower=10.0,
        upper=None,
        expected_error_message="outside threshold requires lower and upper only",
    ),
    InvalidThresholdBoundTestCase(
        description="outside_with_limit",
        operator=ThresholdOperator.OUTSIDE,
        limit=15.0,
        lower=10.0,
        upper=20.0,
        expected_error_message="outside threshold requires lower and upper only",
    ),
    InvalidThresholdBoundTestCase(
        description="outside_reversed_range",
        operator=ThresholdOperator.OUTSIDE,
        limit=None,
        lower=20.0,
        upper=10.0,
        expected_error_message="outside threshold lower must be less than or equal to upper",
    ),
    InvalidThresholdBoundTestCase(
        description="non_finite_limit",
        operator=ThresholdOperator.BELOW,
        limit=float("nan"),
        lower=None,
        upper=None,
        expected_error_message="measurement threshold limit must be finite",
    ),
)

INVALID_NESTING_CASES: tuple[InvalidThresholdNestingTestCase, ...] = (
    InvalidThresholdNestingTestCase(
        description="mixed_operators",
        warn_operator=ThresholdOperator.BELOW,
        warn_limit=100.0,
        warn_lower=None,
        warn_upper=None,
        error_operator=ThresholdOperator.ABOVE,
        error_limit=101.0,
        error_lower=None,
        error_upper=None,
        expected_error_message="mixed measurement threshold operators are unsupported in v1",
    ),
    InvalidThresholdNestingTestCase(
        description="below_error_not_lower",
        warn_operator=ThresholdOperator.BELOW,
        warn_limit=100.0,
        warn_lower=None,
        warn_upper=None,
        error_operator=ThresholdOperator.BELOW,
        error_limit=100.0,
        error_lower=None,
        error_upper=None,
        expected_error_message="below error limit must be less than warn limit",
    ),
    InvalidThresholdNestingTestCase(
        description="above_error_not_higher",
        warn_operator=ThresholdOperator.ABOVE,
        warn_limit=100.0,
        warn_lower=None,
        warn_upper=None,
        error_operator=ThresholdOperator.ABOVE,
        error_limit=99.0,
        error_lower=None,
        error_upper=None,
        expected_error_message="above error limit must be greater than warn limit",
    ),
    InvalidThresholdNestingTestCase(
        description="outside_error_does_not_contain_warn",
        warn_operator=ThresholdOperator.OUTSIDE,
        warn_limit=None,
        warn_lower=10.0,
        warn_upper=20.0,
        error_operator=ThresholdOperator.OUTSIDE,
        error_limit=None,
        error_lower=9.0,
        error_upper=20.0,
        expected_error_message="outside error range must strictly contain warn range",
    ),
)

INVALID_CONTRACT_CASES: tuple[InvalidMeasurementContractTestCase, ...] = (
    InvalidMeasurementContractTestCase(
        description="empty_value_column",
        value_column=" ",
        sample_count_column=None,
        sample_unit=None,
        expected_error_message="measurement contract value_column must be non-empty",
    ),
    InvalidMeasurementContractTestCase(
        description="empty_sample_count_column",
        value_column="rate",
        sample_count_column="",
        sample_unit=None,
        expected_error_message="measurement contract sample_count_column must be non-empty",
    ),
    InvalidMeasurementContractTestCase(
        description="empty_sample_unit",
        value_column="rate",
        sample_count_column="count",
        sample_unit=" ",
        expected_error_message="measurement contract sample_unit must be non-empty",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidThresholdBoundTestCase(
            description=case.description,
            operator=case.operator,
            limit=case.limit,
            lower=case.lower,
            upper=case.upper,
            expected_error_message=case.expected_error_message,
        )
        for case in INVALID_BOUND_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_bound_shape_when_constructing_then_raises_clear_error(
    test_case: InvalidThresholdBoundTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_message):
        build_measurement_threshold_bound(
            operator=test_case.operator,
            limit=test_case.limit,
            lower=test_case.lower,
            upper=test_case.upper,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidThresholdPolicyTestCase(
            description="no_thresholds",
            expected_error_message="at least one measurement threshold is required",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_no_thresholds_when_constructing_policy_then_raises_clear_error(
    test_case: InvalidThresholdPolicyTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_message):
        MeasurementThresholds()


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidThresholdNestingTestCase(
            description=case.description,
            warn_operator=case.warn_operator,
            warn_limit=case.warn_limit,
            warn_lower=case.warn_lower,
            warn_upper=case.warn_upper,
            error_operator=case.error_operator,
            error_limit=case.error_limit,
            error_lower=case.error_lower,
            error_upper=case.error_upper,
            expected_error_message=case.expected_error_message,
        )
        for case in INVALID_NESTING_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_threshold_nesting_when_constructing_then_raises_clear_error(
    test_case: InvalidThresholdNestingTestCase,
) -> None:
    warn: MeasurementThresholdBound = build_measurement_threshold_bound(
        operator=test_case.warn_operator,
        limit=test_case.warn_limit,
        lower=test_case.warn_lower,
        upper=test_case.warn_upper,
    )
    error: MeasurementThresholdBound = build_measurement_threshold_bound(
        operator=test_case.error_operator,
        limit=test_case.error_limit,
        lower=test_case.error_lower,
        upper=test_case.error_upper,
    )

    with pytest.raises(ValueError, match=test_case.expected_error_message):
        MeasurementThresholds(warn=warn, error=error)


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidMeasurementContractTestCase(
            description=case.description,
            value_column=case.value_column,
            sample_count_column=case.sample_count_column,
            sample_unit=case.sample_unit,
            expected_error_message=case.expected_error_message,
        )
        for case in INVALID_CONTRACT_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_empty_contract_field_when_constructing_then_raises_clear_error(
    test_case: InvalidMeasurementContractTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_message):
        MeasurementContract(
            value_column=test_case.value_column,
            sample_count_column=test_case.sample_count_column,
            sample_unit=test_case.sample_unit,
        )
