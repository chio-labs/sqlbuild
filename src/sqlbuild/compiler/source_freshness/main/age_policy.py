"""Public source freshness age policy evaluation entrypoint."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.source_freshness.helpers.age_policy import (
    evaluate_source_freshness_age_policy as _evaluate_source_freshness_age_policy,
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

    return _evaluate_source_freshness_age_policy(
        policy=policy,
        data_version=data_version,
        observed_at=observed_at,
    )
