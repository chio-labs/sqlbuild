"""Execution history filter validation contract tests."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from sqlbuild.execution_history import EventFamily, EventFilter, InvalidFilterError, RunFilter
from tests.unit.src.sqlbuild.runtime.execution_history.conformance._test_types import (
    FilterValidationCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FilterValidationCase(
            description="empty event invocation ID",
            filter_factory=lambda: EventFilter(invocation_id=""),
            expected_error="invocation_id.*non-empty",
        ),
        FilterValidationCase(
            description="blank event run ID",
            filter_factory=lambda: EventFilter(run_id=" "),
            expected_error="run_id.*non-empty",
        ),
        FilterValidationCase(
            description="empty event producer",
            filter_factory=lambda: EventFilter(producer=""),
            expected_error="producer.*non-empty",
        ),
        FilterValidationCase(
            description="blank exact event type",
            filter_factory=lambda: EventFilter(event_types=(" ",)),
            expected_error="event_types.*non-empty",
        ),
        FilterValidationCase(
            description="exact types and family are mutually exclusive",
            filter_factory=lambda: EventFilter(
                event_types=("run_started",), family=EventFamily.RUN
            ),
            expected_error="mutually exclusive",
        ),
        FilterValidationCase(
            description="event range is ordered",
            filter_factory=lambda: EventFilter(
                occurred_at_start=datetime(2026, 1, 2, tzinfo=UTC),
                occurred_at_end=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            expected_error="must not be after",
        ),
        FilterValidationCase(
            description="event start uses UTC",
            filter_factory=lambda: EventFilter(
                occurred_at_start=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=1)))
            ),
            expected_error="occurred_at_start must use UTC",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_event_filter_when_constructing_then_actionable_filter_error_is_raised(
    test_case: FilterValidationCase,
) -> None:
    with pytest.raises(InvalidFilterError, match=test_case.expected_error):
        test_case.filter_factory()


@pytest.mark.parametrize(
    "test_case",
    [
        FilterValidationCase(
            description="empty run invocation ID",
            filter_factory=lambda: RunFilter(invocation_id=""),
            expected_error="invocation_id.*non-empty",
        ),
        FilterValidationCase(
            description="run range is ordered",
            filter_factory=lambda: RunFilter(
                created_at_start=datetime(2026, 1, 2, tzinfo=UTC),
                created_at_end=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            expected_error="must not be after",
        ),
        FilterValidationCase(
            description="run end uses UTC",
            filter_factory=lambda: RunFilter(
                created_at_end=datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=-1)))
            ),
            expected_error="created_at_end must use UTC",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_malformed_run_filter_when_constructing_then_actionable_filter_error_is_raised(
    test_case: FilterValidationCase,
) -> None:
    with pytest.raises(InvalidFilterError, match=test_case.expected_error):
        test_case.filter_factory()
