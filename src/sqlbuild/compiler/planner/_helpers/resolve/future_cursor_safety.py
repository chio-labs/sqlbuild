"""Future cursor safety calculation."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from sqlbuild.compiler.planner.exceptions import FutureCursorSafetyError
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    CursorInputEvidence,
    Duration,
    FutureCursorSafetyEvidence,
)
from sqlbuild.compiler.planner.types import CursorGrain, CursorType
from sqlbuild.cursor_algebra.main.compare import compare
from sqlbuild.cursor_algebra.main.floor_to_grain import floor_to_grain
from sqlbuild.cursor_algebra.main.next_boundary import next_boundary
from sqlbuild.cursor_algebra.main.render import render
from sqlbuild.cursor_algebra.main.sentinel_to_token import sentinel_to_token
from sqlbuild.cursor_algebra.models import DateValue, TimestampValue
from sqlbuild.cursor_algebra.types import CursorScalar
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
    if not isinstance(bounds.start, DateValue | TimestampValue) or not isinstance(
        bounds.end, DateValue | TimestampValue
    ):
        return bounds
    allowed_start, allowed_end = _allowed_bounds(
        discovered_end=bounds.end,
        cursor_grain=cursor_grain,
        invocation_time=invocation_time,
        duration=duration,
    )
    future_start_detected: bool = compare(left=bounds.start, right=allowed_start) > 0
    future_end_detected: bool = compare(left=bounds.end, right=allowed_end) > 0
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
    applied_end: CursorScalar = allowed_end if future_end_detected else bounds.end
    return replace(
        bounds,
        end=applied_end,
        future_safety=FutureCursorSafetyEvidence(
            action=config.action,
            max_distance=config.max_distance,
            invocation_time=TimestampValue(value=invocation_time.astimezone(UTC)),
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
    discovered_end: CursorScalar,
    cursor_grain: str | None,
    invocation_time: datetime,
    duration: Duration,
) -> tuple[CursorScalar, CursorScalar]:
    clock: datetime = invocation_time.astimezone(UTC).replace(tzinfo=None)
    maximum: datetime = duration.add_to(clock)
    grain: CursorGrain = CursorGrain(cursor_grain or CursorGrain.SECOND)
    if isinstance(discovered_end, DateValue):
        allowed_start: CursorScalar = floor_to_grain(
            value=DateValue(value=maximum.date()), grain=grain
        )
    elif isinstance(discovered_end, TimestampValue):
        allowed_timestamp: datetime = maximum
        if discovered_end.value.tzinfo is not None:
            allowed_timestamp = allowed_timestamp.replace(tzinfo=UTC)
        allowed_start = floor_to_grain(value=TimestampValue(value=allowed_timestamp), grain=grain)
    else:
        raise FutureCursorSafetyError("future cursor safety requires a timestamp cursor")
    return allowed_start, next_boundary(value=allowed_start, grain=grain)


def _determining_input(
    evidence: tuple[CursorInputEvidence, ...],
) -> CursorInputEvidence | None:
    if not evidence:
        return None
    determining: CursorInputEvidence = evidence[0]
    for item in evidence[1:]:
        if compare(left=item.maximum, right=determining.maximum) < 0:
            determining = item
    return determining


def _error_message(
    *,
    bounds: CursorBounds,
    allowed_start: CursorScalar,
    allowed_end: CursorScalar,
    max_distance: str,
) -> str:
    start: str = sentinel_to_token(sentinel=bounds.start)
    end: str = sentinel_to_token(sentinel=bounds.end)
    return (
        "future cursor safety limit exceeded: effective bounds "
        f"['{start}', '{end}') "
        "exceed maximum allowed bounds "
        f"['{render(value=allowed_start)}', '{render(value=allowed_end)}') "
        f"(cursors.future.max_distance={max_distance})"
    )
