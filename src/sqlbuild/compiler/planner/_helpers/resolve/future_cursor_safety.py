"""Future cursor safety calculation."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

from sqlbuild.compiler.planner.exceptions import FutureCursorSafetyError
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputEvidence,
    Duration,
    FutureCursorSafetyEvidence,
)
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.spec.contracts.constants import ZERO_DAY_CURSOR_DURATION
from sqlbuild.spec.contracts.models import FutureCursorsConfig
from sqlbuild.spec.contracts.types import FutureCursorAction


def resolve_future_cursor_safety(
    *,
    bounds: CursorBounds,
    cursor_type: str | None,
    cursor_grain: str | None,
    config: FutureCursorsConfig | None,
    invocation_time: datetime | None,
    has_complete_override: bool,
    input_evidence: tuple[CursorInputEvidence, ...] = (),
) -> CursorBounds:
    """Apply future cursor policy to effective timestamp bounds."""

    if (
        config is None
        or config.max_distance is None
        or cursor_type != CursorType.TIMESTAMP
        or invocation_time is None
        or has_complete_override
    ):
        return bounds
    duration: Duration | None = (
        Duration()
        if config.max_distance == ZERO_DAY_CURSOR_DURATION
        else Duration.parse(config.max_distance)
    )
    if duration is None:
        raise FutureCursorSafetyError(
            f"invalid cursors.future.max_distance '{config.max_distance}'"
        )
    allowed_start, allowed_end = _allowed_bounds(
        discovered_end=bounds.end,
        cursor_grain=cursor_grain,
        invocation_time=invocation_time,
        duration=duration,
    )
    future_start_detected: bool = _comparison_key(bounds.start) > _comparison_key(allowed_start)
    future_end_detected: bool = _comparison_key(bounds.end) > _comparison_key(allowed_end)
    if not future_start_detected and not future_end_detected:
        return bounds
    determining: CursorInputEvidence | None = _determining_input(input_evidence)
    if config.action == FutureCursorAction.ERROR:
        raise FutureCursorSafetyError(
            _error_message(
                bounds=bounds,
                allowed_start=allowed_start,
                allowed_end=allowed_end,
                max_distance=config.max_distance,
            )
        )
    applied_end: str = allowed_end if future_end_detected else bounds.end
    return replace(
        bounds,
        end=applied_end,
        future_safety=FutureCursorSafetyEvidence(
            action=config.action,
            max_distance=config.max_distance,
            invocation_time=invocation_time.astimezone(UTC).isoformat(),
            discovered_start=bounds.start,
            discovered_end=bounds.end,
            applied_start=bounds.start,
            applied_end=applied_end,
            maximum_allowed_start=allowed_start,
            maximum_allowed_end=allowed_end,
            future_start_detected=future_start_detected,
            future_end_detected=future_end_detected,
            determining_relation=determining.relation if determining is not None else None,
            determining_cursor_column=(
                determining.cursor_column if determining is not None else None
            ),
            inputs=input_evidence,
        ),
    )


def _allowed_bounds(
    *,
    discovered_end: str,
    cursor_grain: str | None,
    invocation_time: datetime,
    duration: Duration,
) -> tuple[str, str]:
    clock: datetime = invocation_time.astimezone(UTC).replace(tzinfo=None)
    maximum: datetime = duration.add_to(clock)
    plain_date: date | None = _plain_date(discovered_end)
    if plain_date is not None:
        allowed_date: date = _floor_date(value=maximum.date(), cursor_grain=cursor_grain)
        return allowed_date.isoformat(), _advance_date(
            value=allowed_date, cursor_grain=cursor_grain
        ).isoformat()
    allowed_timestamp: datetime = _floor_timestamp(value=maximum, cursor_grain=cursor_grain)
    if datetime.fromisoformat(discovered_end).tzinfo is not None:
        allowed_timestamp = allowed_timestamp.replace(tzinfo=UTC)
    return (
        allowed_timestamp.isoformat(),
        _advance_timestamp(value=allowed_timestamp, cursor_grain=cursor_grain).isoformat(),
    )


def _floor_date(*, value: date, cursor_grain: str | None) -> date:
    if cursor_grain == CursorGrain.MONTH:
        return value.replace(day=1)
    if cursor_grain == CursorGrain.YEAR:
        return value.replace(month=1, day=1)
    return value


def _advance_date(*, value: date, cursor_grain: str | None) -> date:
    moment: datetime = datetime.combine(value, time.min)
    if cursor_grain == CursorGrain.MONTH:
        return Duration(months=1).add_to(moment).date()
    if cursor_grain == CursorGrain.YEAR:
        return Duration(years=1).add_to(moment).date()
    return value + timedelta(days=1)


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


def _advance_timestamp(*, value: datetime, cursor_grain: str | None) -> datetime:
    if cursor_grain == CursorGrain.YEAR:
        return Duration(years=1).add_to(value)
    if cursor_grain == CursorGrain.MONTH:
        return Duration(months=1).add_to(value)
    if cursor_grain == CursorGrain.DAY:
        return value + timedelta(days=1)
    if cursor_grain == CursorGrain.HOUR:
        return value + timedelta(hours=1)
    if cursor_grain == CursorGrain.MINUTE:
        return value + timedelta(minutes=1)
    return value + timedelta(seconds=1)


def _comparison_key(value: str) -> datetime:
    plain_date: date | None = _plain_date(value)
    if plain_date is not None:
        return datetime.combine(plain_date, time.min)
    parsed: datetime = datetime.fromisoformat(value)
    return parsed.astimezone(UTC).replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _plain_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _determining_input(
    evidence: tuple[CursorInputEvidence, ...],
) -> CursorInputEvidence | None:
    if not evidence:
        return None
    return min(evidence, key=lambda item: _comparison_key(item.maximum))


def _error_message(
    *, bounds: CursorBounds, allowed_start: str, allowed_end: str, max_distance: str
) -> str:
    return (
        "future cursor safety limit exceeded: effective bounds "
        f"['{bounds.start}', '{bounds.end}') exceed maximum allowed bounds "
        f"['{allowed_start}', '{allowed_end}') "
        f"(cursors.future.max_distance={max_distance})"
    )
