from dataclasses import dataclass

from sqlbuild.compiler.auditing.types import ThresholdOperator


@dataclass(frozen=True)
class InvalidThresholdBoundTestCase:
    description: str
    operator: ThresholdOperator
    limit: float | None
    lower: float | None
    upper: float | None
    expected_error_message: str


@dataclass(frozen=True)
class InvalidThresholdNestingTestCase:
    description: str
    warn_operator: ThresholdOperator
    warn_limit: float | None
    warn_lower: float | None
    warn_upper: float | None
    error_operator: ThresholdOperator
    error_limit: float | None
    error_lower: float | None
    error_upper: float | None
    expected_error_message: str


@dataclass(frozen=True)
class InvalidMeasurementContractTestCase:
    description: str
    value_column: str
    sample_count_column: str | None
    sample_unit: str | None
    expected_error_message: str


@dataclass(frozen=True)
class InvalidThresholdPolicyTestCase:
    description: str
    expected_error_message: str


@dataclass(frozen=True)
class ThresholdLimitCoercionTestCase:
    description: str
    input_limit: int
    expected_limit: float


@dataclass(frozen=True)
class ThresholdRangeCoercionTestCase:
    description: str
    input_lower: int
    input_upper: int
    expected_lower: float
    expected_upper: float


@dataclass(frozen=True)
class BooleanThresholdTestCase:
    description: str
    input_limit: bool
    expected_error_message: str
