"""Maximum automatic cursor-start eligibility policy."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlbuild.compiler.planner._helpers.resolve.cursor import apply_typed_cursor_replay_policy
from sqlbuild.compiler.planner.exceptions import MaximumAutomaticStartError
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    Duration,
    MaximumStartPolicyInputs,
    MaximumStartSafetyEvidence,
    ModelCursorSnapshot,
)
from sqlbuild.compiler.planner.types import (
    CursorGrain,
    CursorType,
    IncrementalStrategy,
)
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.min_bound import min_bound
from sqlbuild.cursor_algebra.main.parse import parse
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.models import DateValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar
from sqlbuild.spec.contracts.constants import ZERO_DAY_CURSOR_DURATION
from sqlbuild.spec.contracts.types import FutureCursorAction


def maximum_allowed_start(
    *, discovered_value: str, cursor_grain: str | None, invocation_time: datetime, max_ahead: str
) -> str:
    """Return the invocation-anchored maximum automatic start in cursor representation."""

    discovered: CursorScalar = parse(raw=discovered_value, cursor_type=CursorType.TIMESTAMP)
    return render(
        value=_maximum_allowed_start(
            discovered_value=discovered,
            cursor_grain=cursor_grain,
            invocation_time=invocation_time,
            max_ahead=max_ahead,
        )
    )


def _maximum_allowed_start(
    *,
    discovered_value: CursorScalar,
    cursor_grain: str | None,
    invocation_time: datetime,
    max_ahead: str,
) -> CursorScalar:
    """Return the invocation-anchored maximum automatic typed start."""

    duration: Duration = _parse_duration(max_ahead)
    clock: datetime = invocation_time.astimezone(UTC).replace(tzinfo=None)
    maximum: datetime = duration.add_to(clock)
    grain: CursorGrain = CursorGrain(cursor_grain or CursorGrain.SECOND)
    if isinstance(discovered_value, DateValue):
        return floor_to_grain(value=DateValue(value=maximum.date()), grain=grain)
    if not isinstance(discovered_value, TimestampValue):
        raise MaximumAutomaticStartError(message="automatic start requires a timestamp cursor")
    if discovered_value.value.tzinfo is not None:
        maximum = maximum.replace(tzinfo=UTC)
    return floor_to_grain(value=TimestampValue(value=maximum), grain=grain)


def apply_maximum_start_policy(
    *,
    bounds: CursorBounds,
    snapshot: ModelCursorSnapshot,
    cursor_type: str | None,
    cursor_grain: str | None,
    cursor_start: str | None,
    lookback: str | None,
    backfill_duration: str | None,
    policy: MaximumStartPolicyInputs,
    has_start_override: bool,
) -> CursorBounds:
    """Replace an ineligible physical start before applying normal replay policy."""

    physical_max: CursorScalar | None = snapshot.physical_target_max or snapshot.target_max
    if (
        policy.config is None
        or policy.config.max_ahead is None
        or cursor_type != CursorType.TIMESTAMP
        or policy.invocation_time is None
        or has_start_override
        or physical_max is None
    ):
        return bounds
    if not isinstance(bounds.start, DateValue | TimestampValue) or not isinstance(
        bounds.end, DateValue | TimestampValue
    ):
        return bounds
    horizon: CursorScalar = _maximum_allowed_start(
        discovered_value=physical_max,
        cursor_grain=cursor_grain,
        invocation_time=policy.invocation_time,
        max_ahead=policy.config.max_ahead,
    )
    if compare(left=physical_max, right=horizon) <= 0:
        return bounds
    eligible_start: CursorScalar | None = snapshot.target_eligible_max
    if eligible_start is None and snapshot.upstream_mins:
        upstream_minimum: CursorScalar = min_bound(
            values=snapshot.upstream_mins, cursor_type=CursorType.TIMESTAMP
        )
        if compare(left=upstream_minimum, right=horizon) <= 0:
            eligible_start = upstream_minimum
    if eligible_start is None:
        parsed_cursor_start: CursorScalar | None = (
            parse(raw=cursor_start, cursor_type=CursorType.TIMESTAMP)
            if cursor_start is not None
            else None
        )
        if (
            parsed_cursor_start is not None
            and compare(left=parsed_cursor_start, right=horizon) <= 0
        ):
            eligible_start = parsed_cursor_start
    effective_start: CursorScalar = (
        apply_typed_cursor_replay_policy(
            start=eligible_start,
            end=bounds.end,
            cursor_start=cursor_start,
            cursor_type=cursor_type,
            lookback=lookback,
            backfill_duration=backfill_duration,
            has_start_override=False,
        )
        if eligible_start is not None
        else bounds.start
    )
    evidence: MaximumStartSafetyEvidence = MaximumStartSafetyEvidence(
        action=policy.config.action,
        max_ahead=policy.config.max_ahead,
        invocation_time=TimestampValue(value=policy.invocation_time.astimezone(UTC)),
        physical_target_max=physical_max,
        highest_eligible_target_max=snapshot.target_eligible_max,
        effective_start=effective_start,
        maximum_allowed_start=horizon,
        target_relation=snapshot.target_relation or "",
        cursor_column=snapshot.destination_cursor_column or "",
    )
    if policy.config.action == FutureCursorAction.ERROR:
        raise MaximumAutomaticStartError(evidence=evidence)
    if eligible_start is None or compare(left=effective_start, right=horizon) > 0:
        raise MaximumAutomaticStartError(evidence=evidence)
    idempotent: bool = policy.incremental_strategy in {
        IncrementalStrategy.DELETE_INSERT,
        IncrementalStrategy.MERGE,
    }
    if not idempotent:
        raise MaximumAutomaticStartError(evidence=evidence, non_idempotent=True)
    return replace(bounds, start=effective_start, maximum_start_safety=evidence)


def _parse_duration(value: str) -> Duration:
    parsed: Duration | None = Duration.parse(value)
    if parsed is not None:
        return parsed
    if value == ZERO_DAY_CURSOR_DURATION:
        return Duration()
    raise MaximumAutomaticStartError(message=f"invalid cursors.start.max_ahead '{value}'")
