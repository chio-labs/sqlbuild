"""Build an outside-range audit bound."""

from sqlbuild._native import MeasurementThresholdBound
from sqlbuild.compiler.auditing.types import ThresholdOperator


def outside(*, lower: float, upper: float) -> MeasurementThresholdBound:
    """Return a threshold that matches values outside the inclusive range."""

    return MeasurementThresholdBound(
        operator=ThresholdOperator.OUTSIDE,
        lower=lower,
        upper=upper,
    )
