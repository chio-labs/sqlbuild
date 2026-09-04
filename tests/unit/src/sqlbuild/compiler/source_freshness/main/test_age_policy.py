from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sqlbuild.compiler.source_freshness.main.age_policy import (
    evaluate_source_freshness_age_policy,
)
from sqlbuild.compiler.source_freshness.types import SourceFreshnessAgeStatus
from sqlbuild.spec.contracts.models import SourceFreshnessAgePolicy
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    SourceFreshnessAgeEvaluationTestCase,
    SourceFreshnessNaiveDatetimeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SourceFreshnessAgeEvaluationTestCase(
            description="fresh timestamp passes",
            data_version=datetime(2026, 1, 15, 11, 30, tzinfo=UTC),
            observed_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            expected_status="pass",
        ),
        SourceFreshnessAgeEvaluationTestCase(
            description="stale timestamp warns",
            data_version=datetime(2026, 1, 15, 10, 30, tzinfo=UTC),
            observed_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            expected_status="warn",
        ),
        SourceFreshnessAgeEvaluationTestCase(
            description="stale timestamp errors",
            data_version=datetime(2026, 1, 15, 9, 30, tzinfo=UTC),
            observed_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            expected_status="error",
        ),
        SourceFreshnessAgeEvaluationTestCase(
            description="offset timestamp compares by instant",
            data_version=datetime(2026, 1, 15, 4, 30, tzinfo=timezone(timedelta(hours=-5))),
            observed_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            expected_status="error",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_aware_timestamp_when_evaluating_age_then_preserves_threshold_behavior(
    test_case: SourceFreshnessAgeEvaluationTestCase,
) -> None:
    result: SourceFreshnessAgeStatus | None = evaluate_source_freshness_age_policy(
        policy=SourceFreshnessAgePolicy(warn_after="1h", error_after="2h"),
        data_version=test_case.data_version,
        observed_at=test_case.observed_at,
    )

    assert result == test_case.expected_status


@pytest.mark.parametrize(
    "test_case",
    (
        SourceFreshnessNaiveDatetimeTestCase(
            description="naive age data version is rejected",
            naive_value=datetime(2026, 1, 15, 11, 30),
            expected_error_fragment="data_version must be timezone-aware",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_naive_timestamp_when_evaluating_age_then_rejects_it(
    test_case: SourceFreshnessNaiveDatetimeTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        evaluate_source_freshness_age_policy(
            policy=SourceFreshnessAgePolicy(warn_after="1h"),
            data_version=test_case.naive_value,
            observed_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
