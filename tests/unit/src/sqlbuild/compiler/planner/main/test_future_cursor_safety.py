from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.planner.exceptions import FutureCursorSafetyError
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.main.execution.future_cursor_warning import future_cursor_cap_warning
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.spec.contracts.models import FutureCursorsConfig
from sqlbuild.spec.contracts.types import FutureCursorAction
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import FutureCursorSafetyTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        FutureCursorSafetyTestCase(
            description="timestamp cap advances equality horizon by one second",
            bounds=CursorBounds("2026-09-01T00:00:00", "2030-01-01T00:00:01"),
            config=FutureCursorsConfig("2d", FutureCursorAction.CAP),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.SECOND,
            has_complete_override=False,
            expected_start="2026-09-01T00:00:00",
            expected_end="2026-09-03T12:00:01",
            expected_has_safety=True,
        ),
        FutureCursorSafetyTestCase(
            description="date cap retains final inclusive day",
            bounds=CursorBounds("2026-09-01", "2030-01-02"),
            config=FutureCursorsConfig("2d", FutureCursorAction.CAP),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.DAY,
            has_complete_override=False,
            expected_start="2026-09-01",
            expected_end="2026-09-04",
            expected_has_safety=True,
        ),
        FutureCursorSafetyTestCase(
            description="future start is preserved when end is within horizon",
            bounds=CursorBounds("2030-01-01", "2026-09-02"),
            config=FutureCursorsConfig("2d", FutureCursorAction.CAP),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.DAY,
            has_complete_override=False,
            expected_start="2030-01-01",
            expected_end="2026-09-02",
            expected_has_safety=True,
        ),
        FutureCursorSafetyTestCase(
            description="month grain caps at next month boundary",
            bounds=CursorBounds("2026-01-01T00:00:00", "2030-01-01T00:00:00"),
            config=FutureCursorsConfig("1mo", FutureCursorAction.CAP),
            invocation_time=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.MONTH,
            has_complete_override=False,
            expected_start="2026-01-01T00:00:00",
            expected_end="2026-03-01T00:00:00",
            expected_has_safety=True,
        ),
        FutureCursorSafetyTestCase(
            description="year grain caps at next year boundary",
            bounds=CursorBounds("2026-01-01T00:00:00", "2030-01-01T00:00:00"),
            config=FutureCursorsConfig("1y", FutureCursorAction.CAP),
            invocation_time=datetime(2026, 6, 15, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.YEAR,
            has_complete_override=False,
            expected_start="2026-01-01T00:00:00",
            expected_end="2028-01-01T00:00:00",
            expected_has_safety=True,
        ),
        FutureCursorSafetyTestCase(
            description="exclusive end equal to horizon is accepted",
            bounds=CursorBounds("2026-09-01T00:00:00", "2026-09-03T12:00:01"),
            config=FutureCursorsConfig("2d", FutureCursorAction.ERROR),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.SECOND,
            has_complete_override=False,
            expected_start="2026-09-01T00:00:00",
            expected_end="2026-09-03T12:00:01",
            expected_has_safety=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_effective_cursor_when_applying_cap_then_expected_bounds_are_returned(
    test_case: FutureCursorSafetyTestCase,
) -> None:
    result: CursorBounds = apply_future_cursor_safety(
        bounds=test_case.bounds,
        cursor_type=CursorType.TIMESTAMP,
        cursor_grain=test_case.cursor_grain,
        config=test_case.config,
        invocation_time=test_case.invocation_time,
        has_complete_override=test_case.has_complete_override,
    )

    assert result.start == test_case.expected_start
    assert result.end == test_case.expected_end
    assert (result.future_safety is not None) is test_case.expected_has_safety
    assert (future_cursor_cap_warning(result) is not None) is test_case.expected_has_safety


@pytest.mark.parametrize(
    "test_case",
    [
        FutureCursorSafetyTestCase(
            description="future end fails closed",
            bounds=CursorBounds("2026-09-01", "2030-01-01"),
            config=FutureCursorsConfig("2d", FutureCursorAction.ERROR),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.DAY,
            has_complete_override=False,
            expected_start="2026-09-01",
            expected_end="2030-01-01",
            expected_has_safety=False,
            expected_error_fragment="future cursor safety limit exceeded",
        ),
        FutureCursorSafetyTestCase(
            description="future start independently fails closed",
            bounds=CursorBounds("2030-01-01", "2026-09-02"),
            config=FutureCursorsConfig("2d", FutureCursorAction.ERROR),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.DAY,
            has_complete_override=False,
            expected_start="2030-01-01",
            expected_end="2026-09-02",
            expected_has_safety=False,
            expected_error_fragment="future cursor safety limit exceeded",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_future_effective_cursor_when_applying_error_then_fails_closed(
    test_case: FutureCursorSafetyTestCase,
) -> None:
    with pytest.raises(FutureCursorSafetyError, match=test_case.expected_error_fragment):
        apply_future_cursor_safety(
            bounds=test_case.bounds,
            cursor_type=CursorType.TIMESTAMP,
            cursor_grain=test_case.cursor_grain,
            config=test_case.config,
            invocation_time=test_case.invocation_time,
            has_complete_override=test_case.has_complete_override,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        FutureCursorSafetyTestCase(
            description="complete override bypasses safety",
            bounds=CursorBounds("2029-01-01", "2030-01-01"),
            config=FutureCursorsConfig("2d", FutureCursorAction.ERROR),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.DAY,
            has_complete_override=True,
            expected_start="2029-01-01",
            expected_end="2030-01-01",
            expected_has_safety=False,
        ),
        FutureCursorSafetyTestCase(
            description="absent max distance disables safety",
            bounds=CursorBounds("2026-09-01", "2030-01-01"),
            config=FutureCursorsConfig(action=FutureCursorAction.ERROR),
            invocation_time=datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
            cursor_grain=CursorGrain.DAY,
            has_complete_override=False,
            expected_start="2026-09-01",
            expected_end="2030-01-01",
            expected_has_safety=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_bypass_condition_when_applying_safety_then_bounds_are_unchanged(
    test_case: FutureCursorSafetyTestCase,
) -> None:
    result: CursorBounds = apply_future_cursor_safety(
        bounds=test_case.bounds,
        cursor_type=CursorType.TIMESTAMP,
        cursor_grain=test_case.cursor_grain,
        config=test_case.config,
        invocation_time=test_case.invocation_time,
        has_complete_override=test_case.has_complete_override,
    )

    assert result.start == test_case.expected_start
    assert result.end == test_case.expected_end
    assert (result.future_safety is not None) is test_case.expected_has_safety
