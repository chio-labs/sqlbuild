from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessObservation,
    SourceFreshnessRecord,
)
from sqlbuild.spec.contracts.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from tests.unit.src.sqlbuild.compiler.source_freshness.main._test_types import (
    SourceFreshnessDatetimeNormalizationTestCase,
    SourceFreshnessNaiveDatetimeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        SourceFreshnessDatetimeNormalizationTestCase(
            description="offset aware observation normalizes to UTC",
            data_version=datetime(
                2026, 1, 15, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
            ),
            observed_at=datetime(
                2026, 1, 15, 18, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
            ),
            expected_data_version=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            expected_observed_at=datetime(2026, 1, 15, 13, 0, tzinfo=UTC),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_offset_aware_observation_when_constructing_then_normalizes_timestamps_to_utc(
    test_case: SourceFreshnessDatetimeNormalizationTestCase,
) -> None:
    observation: SourceFreshnessObservation = SourceFreshnessObservation(
        source_name="raw.orders",
        strategy=SourceFreshnessStrategy.COLUMN,
        data_version=test_case.data_version,
        value_kind=SourceFreshnessValueKind.TIMESTAMP,
        observed_at=test_case.observed_at,
    )

    assert observation.data_version == test_case.expected_data_version
    assert observation.observed_at == test_case.expected_observed_at


@pytest.mark.parametrize(
    "test_case",
    (
        SourceFreshnessNaiveDatetimeTestCase(
            description="naive observation time is rejected",
            naive_value=datetime(2026, 1, 15, 12, 0),
            expected_error_fragment="observed_at must be timezone-aware",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_naive_observation_time_when_constructing_then_rejects_it(
    test_case: SourceFreshnessNaiveDatetimeTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        SourceFreshnessObservation(
            source_name="raw.orders",
            strategy=SourceFreshnessStrategy.COLUMN,
            data_version=42,
            value_kind=SourceFreshnessValueKind.INTEGER,
            observed_at=test_case.naive_value,
        )


@pytest.mark.parametrize(
    "test_case",
    (
        SourceFreshnessNaiveDatetimeTestCase(
            description="naive record time is rejected",
            naive_value=datetime(2026, 1, 15, 12, 0),
            expected_error_fragment="observed_at must be timezone-aware",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_naive_record_time_when_constructing_then_rejects_it(
    test_case: SourceFreshnessNaiveDatetimeTestCase,
) -> None:
    with pytest.raises(ValueError, match=test_case.expected_error_fragment):
        SourceFreshnessRecord(
            source_name="raw.orders",
            target_database=None,
            target_schema="raw",
            target_name="orders",
            run_id="run_001",
            strategy="column",
            value_kind="integer",
            data_version="42",
            data_version_hash="hash_orders",
            observed_at=test_case.naive_value,
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
