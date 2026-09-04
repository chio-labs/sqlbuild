from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone, tzinfo

import pytest

from sqlbuild.cli.commands.main.execution import _freshness
from tests.unit.src.sqlbuild.cli.commands.main.execution._test_types import FreshnessClockTestCase


class NonUtcLocalDateTime:
    non_utc_local_time: datetime = datetime(
        2026, 1, 15, 17, 30, tzinfo=timezone(timedelta(hours=5, minutes=30))
    )

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> datetime:
        assert tz is UTC
        return datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "test_case",
    (
        FreshnessClockTestCase(
            description="non UTC local timezone still observes in UTC",
            expected_observed_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_non_utc_local_timezone_when_observing_freshness_then_clock_returns_aware_utc(
    monkeypatch: pytest.MonkeyPatch,
    test_case: FreshnessClockTestCase,
) -> None:
    monkeypatch.setattr(_freshness, "datetime", NonUtcLocalDateTime)

    observed_at: datetime = _freshness._source_freshness_observed_at()

    assert observed_at == test_case.expected_observed_at
    assert observed_at.tzinfo is UTC


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
