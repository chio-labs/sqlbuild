from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.source_freshness._helpers.age_policy import (
    evaluate_source_freshness_age_policy,
)
from sqlbuild.spec.contracts.models import SourceFreshnessAgePolicy
from tests.unit.src.sqlbuild.compiler.source_freshness._helpers._test_types import (
    SourceFreshnessAgePolicyDurationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SourceFreshnessAgePolicyDurationTestCase(
            description="unknown unit is rejected instead of computed as minutes",
            warn_after="1w",
            expected_error_fragment="must be a positive duration",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unknown_age_policy_unit_when_evaluating_then_raises_value_error(
    test_case: SourceFreshnessAgePolicyDurationTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        evaluate_source_freshness_age_policy(
            policy=SourceFreshnessAgePolicy(warn_after=test_case.warn_after),
            data_version=datetime(2026, 1, 1, tzinfo=UTC),
            observed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
