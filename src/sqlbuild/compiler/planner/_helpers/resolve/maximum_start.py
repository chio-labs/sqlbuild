"""Maximum automatic cursor-start eligibility policy."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time

from sqlbuild.compiler.planner._helpers.resolve.cursor import apply_cursor_replay_policy
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
from sqlbuild.spec.contracts.constants import ZERO_DAY_CURSOR_DURATION
from sqlbuild.spec.contracts.types import FutureCursorAction


def maximum_allowed_start(
    *, discovered_value: str, cursor_grain: str | None, invocation_time: datetime, max_ahead: str
) -> str:
    """Return the invocation-anchored maximum automatic start in cursor representation."""

    duration: Duration = _parse_duration(max_ahead)
    clock: datetime = invocation_time.astimezone(UTC).replace(tzinfo=None)
    maximum: datetime = duration.add_to(clock)
    try:
        plain_date: date = date.fromisoformat(discovered_value)
    except ValueError:
        plain_date = date.min
    if plain_date != date.min:
        return _floor_timestamp(value=maximum, cursor_grain=cursor_grain).date().isoformat()
    normalized: datetime = _floor_timestamp(value=maximum, cursor_grain=cursor_grain)
    parsed: datetime = datetime.fromisoformat(discovered_value)
    if parsed.tzinfo is not None:
        normalized = normalized.replace(tzinfo=UTC)
    return normalized.isoformat()


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

    physical_max: str | None = snapshot.physical_target_max or snapshot.target_max
    if (
        policy.config is None
        or policy.config.max_ahead is None
        or cursor_type != CursorType.TIMESTAMP
        or policy.invocation_time is None
        or has_start_override
        or physical_max is None
    ):
        return bounds
    horizon: str = maximum_allowed_start(
        discovered_value=physical_max,
        cursor_grain=cursor_grain,
        invocation_time=policy.invocation_time,
        max_ahead=policy.config.max_ahead,
    )
    if _comparison_key(physical_max) <= _comparison_key(horizon):
        return bounds
    eligible_start: str | None = snapshot.target_eligible_max
    if eligible_start is None and snapshot.upstream_mins:
        upstream_minimum: str = min(snapshot.upstream_mins, key=_comparison_key)
        if _comparison_key(upstream_minimum) <= _comparison_key(horizon):
            eligible_start = upstream_minimum
    if eligible_start is None:
        if cursor_start is not None and _comparison_key(cursor_start) <= _comparison_key(horizon):
            eligible_start = cursor_start
    effective_start: str = (
        apply_cursor_replay_policy(
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
        invocation_time=policy.invocation_time.astimezone(UTC).isoformat(),
        physical_target_max=physical_max,
        highest_eligible_target_max=snapshot.target_eligible_max,
        effective_start=effective_start,
        maximum_allowed_start=horizon,
        target_relation=snapshot.target_relation or "",
        cursor_column=snapshot.destination_cursor_column or "",
    )
    if policy.config.action == FutureCursorAction.ERROR:
        raise MaximumAutomaticStartError(evidence=evidence)
    if eligible_start is None or _comparison_key(effective_start) > _comparison_key(horizon):
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


def _floor_timestamp(*, value: datetime, cursor_grain: str | None) -> datetime:
    if cursor_grain == CursorGrain.YEAR:
        return value.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    if cursor_grain == CursorGrain.MONTH:
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if cursor_grain == CursorGrain.DAY:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    if cursor_grain == CursorGrain.HOUR:
        return value.replace(minute=0, second=0, microsecond=0)
    if cursor_grain == CursorGrain.MINUTE:
        return value.replace(second=0, microsecond=0)
    return value.replace(microsecond=0)


def _comparison_key(value: str) -> datetime:
    try:
        return datetime.combine(date.fromisoformat(value), time.min)
    except ValueError:
        parsed: datetime = datetime.fromisoformat(value)
        return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo is not None else parsed
