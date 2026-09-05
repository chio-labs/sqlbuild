"""Evaluate a measurement against its sample and threshold policy."""

from __future__ import annotations

from math import isfinite
from typing import cast

from sqlbuild.compiler.auditing.exceptions import MeasurementAuditError
from sqlbuild.compiler.auditing.models import (
    MeasurementThresholdBound,
    MeasurementThresholds,
)
from sqlbuild.compiler.auditing.types import AuditOutcome, ThresholdOperator


def evaluate_measurement(
    *,
    measured_value: float,
    sample_count: int | None,
    minimum_samples: int | None,
    thresholds: MeasurementThresholds,
) -> AuditOutcome:
    """Return the canonical outcome for one finite measured value."""

    if not isfinite(measured_value):
        raise MeasurementAuditError("measured_value must be finite")
    if minimum_samples is not None and (sample_count is None or sample_count < minimum_samples):
        return AuditOutcome.INSUFFICIENT
    if thresholds.error is not None and _violates_bound(
        measured_value=measured_value, bound=thresholds.error
    ):
        return AuditOutcome.ERROR
    if thresholds.warn is not None and _violates_bound(
        measured_value=measured_value, bound=thresholds.warn
    ):
        return AuditOutcome.WARN
    return AuditOutcome.PASS


def _violates_bound(*, measured_value: float, bound: MeasurementThresholdBound) -> bool:
    if bound.operator == ThresholdOperator.BELOW:
        return measured_value < cast(float, bound.limit)
    if bound.operator == ThresholdOperator.ABOVE:
        return measured_value > cast(float, bound.limit)
    return measured_value < cast(float, bound.lower) or measured_value > cast(float, bound.upper)
