"""Build an above-threshold audit bound."""

from sqlbuild._native import MeasurementThresholdBound
from sqlbuild.compiler.auditing.types import ThresholdOperator


def above(limit: float) -> MeasurementThresholdBound:
    """Return a threshold that matches values above ``limit``."""

    return MeasurementThresholdBound(operator=ThresholdOperator.ABOVE, limit=limit)
