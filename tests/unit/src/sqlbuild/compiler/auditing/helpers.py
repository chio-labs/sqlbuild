"""Test helpers for auditing domain models."""

from sqlbuild.compiler.auditing.models import MeasurementThresholdBound
from sqlbuild.compiler.auditing.types import ThresholdOperator


def build_measurement_threshold_bound(
    *,
    operator: ThresholdOperator,
    limit: float | None,
    lower: float | None,
    upper: float | None,
) -> MeasurementThresholdBound:
    return MeasurementThresholdBound(
        operator=operator,
        limit=limit,
        lower=lower,
        upper=upper,
    )
