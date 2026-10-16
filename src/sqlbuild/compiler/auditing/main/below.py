"""Build a below-threshold audit bound."""

from sqlbuild._native import MeasurementThresholdBound
from sqlbuild.compiler.auditing.types import ThresholdOperator


def below(limit: float) -> MeasurementThresholdBound:
    """Return a threshold that matches values below ``limit``."""

    return MeasurementThresholdBound(operator=ThresholdOperator.BELOW, limit=limit)
