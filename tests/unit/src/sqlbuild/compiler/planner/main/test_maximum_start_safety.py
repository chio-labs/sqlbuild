"""Tests for maximum automatic-start eligibility policy."""

from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from sqlbuild.compiler.planner._helpers.resolve.cursor import compute_cursor_bounds
from sqlbuild.compiler.planner.exceptions import MaximumAutomaticStartError
from sqlbuild.compiler.planner.main.execution.future_cursor_safety import apply_future_cursor_safety
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
)
from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.spec.contracts.models import FutureCursorsConfig, StartCursorsConfig
from sqlbuild.spec.contracts.types import FutureCursorAction
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    MaximumStartCapTestCase,
    MaximumStartErrorTestCase,
    MaximumStartFutureEndInteractionTestCase,
    MaximumStartUnsafeFallbackTestCase,
)

_CAP_CASES: tuple[MaximumStartCapTestCase, ...] = (
    MaximumStartCapTestCase(
        description="date target uses eligible max then lookback",
        target_max="2026-09-03",
        target_eligible_max="2026-09-01",
        upstream_min="2026-08-01",
        upstream_max="2026-09-03",
        cursor_type="timestamp",
        cursor_grain="day",
        lookback="2d",
        start_override=None,
        incremental_strategy="delete_insert",
        expected_start="2026-08-30T00:00:00",
        expected_has_safety=True,
    ),
    MaximumStartCapTestCase(
        description="timestamp target is normalized to grain",
        target_max="2026-09-01T14:45:00",
        target_eligible_max="2026-09-01T12:00:00",
        upstream_min="2026-08-01T00:00:00",
        upstream_max="2026-09-01T14:45:00",
        cursor_type="timestamp",
        cursor_grain="hour",
        lookback=None,
        start_override=None,
        incremental_strategy="merge",
        expected_start="2026-09-01T12:00:00",
        expected_has_safety=True,
    ),
    MaximumStartCapTestCase(
        description="no eligible target uses first run minimum",
        target_max="2026-09-03",
        target_eligible_max=None,
        upstream_min="2026-08-01",
        upstream_max="2026-09-03",
        cursor_type="timestamp",
        cursor_grain="day",
        lookback=None,
        start_override=None,
        incremental_strategy="delete_insert",
        expected_start="2026-08-01",
        expected_has_safety=True,
    ),
    MaximumStartCapTestCase(
        description="explicit start bypasses policy",
        target_max="2026-09-03",
        target_eligible_max="2026-09-01",
        upstream_min="2026-08-01",
        upstream_max="2026-09-03",
        cursor_type="timestamp",
        cursor_grain="day",
        lookback="2d",
        start_override="2026-07-01",
        incremental_strategy="append",
        expected_start="2026-07-01",
        expected_has_safety=False,
    ),
    MaximumStartCapTestCase(
        description="integer cursors are unaffected",
        target_max="30",
        target_eligible_max=None,
        upstream_min="1",
        upstream_max="40",
        cursor_type="integer",
        cursor_grain=None,
        lookback=None,
        start_override=None,
        incremental_strategy="append",
        expected_start="30",
        expected_has_safety=False,
    ),
)

_ERROR_CASES: tuple[MaximumStartErrorTestCase, ...] = (
    MaximumStartErrorTestCase(
        description="configured error fails closed",
        action="error",
        incremental_strategy="delete_insert",
        incremental_mode=None,
        expected_error_fragment="maximum automatic start policy exceeded",
    ),
    MaximumStartErrorTestCase(
        description="append recovery fails closed",
        action="cap",
        incremental_strategy="append",
        incremental_mode=None,
        expected_error_fragment="non-idempotent materialization",
    ),
    MaximumStartErrorTestCase(
        description="microbatch append recovery fails closed",
        action="cap",
        incremental_strategy="append",
        incremental_mode="microbatch",
        expected_error_fragment="non-idempotent materialization",
    ),
)

_UNSAFE_FALLBACK_CASES: tuple[MaximumStartUnsafeFallbackTestCase, ...] = (
    MaximumStartUnsafeFallbackTestCase(
        description="all target and upstream values are beyond horizon",
        target_eligible_max=None,
        upstream_min="2026-09-02",
        cursor_start=None,
        expected_error_fragment="maximum automatic start policy exceeded",
    ),
    MaximumStartUnsafeFallbackTestCase(
        description="future cursor start makes otherwise safe first run unsafe",
        target_eligible_max=None,
        upstream_min="2026-08-01",
        cursor_start="2026-09-02",
        expected_error_fragment="maximum automatic start policy exceeded",
    ),
)

_FUTURE_END_INTERACTION_CASES: tuple[MaximumStartFutureEndInteractionTestCase, ...] = (
    MaximumStartFutureEndInteractionTestCase(
        description="two days ahead remains within future end horizon",
        upstream_max="2026-09-03",
        expected_end="2026-09-04",
        expected_future_end_safety=False,
    ),
    MaximumStartFutureEndInteractionTestCase(
        description="distant end is capped independently after start recovery",
        upstream_max="2026-09-10",
        expected_end="2026-09-04",
        expected_future_end_safety=True,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [MaximumStartCapTestCase(**asdict(case)) for case in _CAP_CASES],
    ids=lambda case: case.description,
)
def test_given_target_cursor_when_computing_automatic_start_then_applies_eligibility_before_lookback(
    test_case: MaximumStartCapTestCase,
) -> None:
    bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max=test_case.target_max,
            upstream_mins=(test_case.upstream_min,),
            upstream_maxes=(test_case.upstream_max,),
            target_eligible_max=test_case.target_eligible_max,
            target_relation="analytics.events",
            destination_cursor_column="event_at",
        ),
        cursor_type=test_case.cursor_type,
        cursor_start=None,
        lookback=test_case.lookback,
        backfill_duration=None,
        start_cursor_override=test_case.start_override,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain=test_case.cursor_grain,
        maximum_start_policy=MaximumStartPolicyInputs(
            config=StartCursorsConfig(max_ahead="0d", action=FutureCursorAction.CAP),
            invocation_time=datetime(2026, 9, 1, 12, tzinfo=UTC),
            incremental_strategy=test_case.incremental_strategy,
        ),
    )

    assert bounds is not None
    assert sentinel_to_token(sentinel=bounds.start) == test_case.expected_start
    assert (bounds.maximum_start_safety is not None) is test_case.expected_has_safety


@pytest.mark.parametrize(
    "test_case",
    [MaximumStartErrorTestCase(**asdict(case)) for case in _ERROR_CASES],
    ids=lambda case: case.description,
)
def test_given_unsafe_automatic_start_when_policy_cannot_recover_then_fails_closed(
    test_case: MaximumStartErrorTestCase,
) -> None:
    with pytest.raises(MaximumAutomaticStartError, match=test_case.expected_error_fragment):
        compute_cursor_bounds(
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2026-09-03",
                upstream_mins=("2026-08-01",),
                upstream_maxes=("2026-09-03",),
                target_eligible_max="2026-09-01",
                target_relation="analytics.events",
                destination_cursor_column="event_at",
            ),
            cursor_type="timestamp",
            cursor_start=None,
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            cursor_grain="day",
            maximum_start_policy=MaximumStartPolicyInputs(
                config=StartCursorsConfig(
                    max_ahead="0d", action=FutureCursorAction(test_case.action)
                ),
                invocation_time=datetime(2026, 9, 1, 12, tzinfo=UTC),
                incremental_strategy=test_case.incremental_strategy,
                incremental_mode=test_case.incremental_mode,
            ),
        )


@pytest.mark.parametrize(
    "test_case",
    [MaximumStartUnsafeFallbackTestCase(**asdict(case)) for case in _UNSAFE_FALLBACK_CASES],
    ids=lambda case: case.description,
)
def test_given_only_future_fallbacks_when_capping_automatic_start_then_fails_closed(
    test_case: MaximumStartUnsafeFallbackTestCase,
) -> None:
    with pytest.raises(MaximumAutomaticStartError, match=test_case.expected_error_fragment):
        compute_cursor_bounds(
            cursor_snapshot=ModelCursorSnapshot(
                target_max="2026-09-03",
                upstream_mins=(test_case.upstream_min,),
                upstream_maxes=("2026-09-03",),
                target_eligible_max=test_case.target_eligible_max,
                target_relation="analytics.events",
                destination_cursor_column="event_at",
            ),
            cursor_type="timestamp",
            cursor_start=test_case.cursor_start,
            lookback=None,
            backfill_duration=None,
            start_cursor_override=None,
            end_cursor_override=None,
            is_microbatch=False,
            cursor_grain="day",
            maximum_start_policy=MaximumStartPolicyInputs(
                config=StartCursorsConfig(max_ahead="0d", action=FutureCursorAction.CAP),
                invocation_time=datetime(2026, 9, 1, 12, tzinfo=UTC),
                incremental_strategy="delete_insert",
            ),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        MaximumStartFutureEndInteractionTestCase(**asdict(case))
        for case in _FUTURE_END_INTERACTION_CASES
    ],
    ids=lambda case: case.description,
)
def test_given_future_start_and_end_policies_when_resolving_then_each_horizon_is_independent(
    test_case: MaximumStartFutureEndInteractionTestCase,
) -> None:
    invocation_time: datetime = datetime(2026, 9, 1, 12, tzinfo=UTC)
    start_bounds: CursorBounds | None = compute_cursor_bounds(
        cursor_snapshot=ModelCursorSnapshot(
            target_max="2026-09-03",
            upstream_mins=("2026-08-01",),
            upstream_maxes=(test_case.upstream_max,),
            target_eligible_max="2026-09-01",
            target_relation="analytics.events",
            destination_cursor_column="event_at",
        ),
        cursor_type="timestamp",
        cursor_start=None,
        lookback=None,
        backfill_duration=None,
        start_cursor_override=None,
        end_cursor_override=None,
        is_microbatch=False,
        cursor_grain="day",
        maximum_start_policy=MaximumStartPolicyInputs(
            config=StartCursorsConfig(max_ahead="0d", action=FutureCursorAction.CAP),
            invocation_time=invocation_time,
            incremental_strategy="delete_insert",
        ),
    )
    assert start_bounds is not None

    bounds: CursorBounds = apply_future_cursor_safety(
        bounds=start_bounds,
        cursor_type="timestamp",
        cursor_grain="day",
        config=FutureCursorsConfig(max_distance="2d", action=FutureCursorAction.CAP),
        invocation_time=invocation_time,
        has_complete_override=False,
    )

    assert sentinel_to_token(sentinel=bounds.start) == "2026-09-01"
    assert sentinel_to_token(sentinel=bounds.end) == test_case.expected_end
    assert bounds.maximum_start_safety is not None
    assert (bounds.future_safety is not None) is test_case.expected_future_end_safety
