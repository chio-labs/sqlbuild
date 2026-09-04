"""Source freshness age policy evaluation helpers."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.source_freshness._helpers.datetime import require_aware_utc_datetime
from sqlbuild.compiler.source_freshness.constants import (
    DURATION_DAY_UNIT,
    DURATION_HOUR_UNIT,
)
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.spec.contracts.models import SourceFreshnessAgePolicy


def evaluate_source_freshness_age_policy(
    *,
    policy: SourceFreshnessAgePolicy | None,
    data_version: object,
    observed_at: datetime,
) -> SourceFreshnessAgeStatus | None:
    """Evaluate optional timestamp age policy for one source freshness observation."""

    if policy is None:
        return None
    if not isinstance(data_version, datetime):
        return SourceFreshnessAgeStatus.UNKNOWN
    aware_data_version: datetime = require_aware_utc_datetime(
        value=data_version, field_name="data_version"
    )
    aware_observed_at: datetime = require_aware_utc_datetime(
        value=observed_at, field_name="observed_at"
    )
    age_seconds: float = (aware_observed_at - aware_data_version).total_seconds()
    if policy.error_after is not None and age_seconds > _duration_seconds(policy.error_after):
        return SourceFreshnessAgeStatus.ERROR
    if policy.warn_after is not None and age_seconds > _duration_seconds(policy.warn_after):
        return SourceFreshnessAgeStatus.WARN
    return SourceFreshnessAgeStatus.PASS


def _duration_seconds(value: str) -> int:
    amount: int = int(value[:-1])
    unit: str = value[-1]
    if unit == DURATION_DAY_UNIT:
        return amount * 24 * 60 * 60
    if unit == DURATION_HOUR_UNIT:
        return amount * 60 * 60
    return amount * 60
