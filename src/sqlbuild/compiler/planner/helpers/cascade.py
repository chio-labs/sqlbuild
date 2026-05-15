"""Backfill cascade propagation through the dependency graph."""

from __future__ import annotations

import re
from datetime import timedelta

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CascadeCause,
    CascadeResult,
)
from sqlbuild.compiler.planner.types import BackfillAction, PlanReason

_DURATION_PATTERN: re.Pattern[str] = re.compile(r"^(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_ACTION_RANK: dict[BackfillAction, int] = {
    BackfillAction.WARN_ONLY: 0,
    BackfillAction.BOUNDED: 1,
    BackfillAction.FULL: 2,
}


def resolve_cascade(
    *,
    model_name: str,
    own_backfill: BackfillResult,
    own_cursor_type: str | None,
    upstream_keys: tuple[CompiledObjectKey, ...],
    effective_cascades: dict[str, CascadeResult],
    model_cursor_types: dict[str, str | None],
) -> CascadeResult | None:
    """Resolve the effective backfill for a model after upstream cascade propagation.

    Returns None if no upstream produces a stronger effective window than the
    model's own backfill. Returns a CascadeResult with the effective window,
    all contributing upstream causes, and the nominated root decider.
    """

    candidates: list[CascadeCause] = _gather_cascade_candidates(
        own_cursor_type=own_cursor_type,
        upstream_keys=upstream_keys,
        effective_cascades=effective_cascades,
        model_cursor_types=model_cursor_types,
    )

    if not candidates:
        return None

    winning: CascadeCause | None = _pick_winner(candidates=candidates, own_backfill=own_backfill)
    if winning is None:
        return None

    return CascadeResult(
        effective_action=winning.effective_action,
        effective_duration=winning.effective_duration,
        root_cause=winning.root_cause or winning.model_name,
        root_reason=winning.root_reason,
        causes=tuple(candidates),
    )


def build_self_cascade(
    backfill: BackfillResult,
    *,
    root_cause: str | None = None,
    root_reason: PlanReason | None = None,
) -> CascadeResult:
    """Build a CascadeResult representing a model's own backfill for the accumulator."""

    return CascadeResult(
        effective_action=backfill.action,
        effective_duration=backfill.duration,
        root_cause=root_cause,
        root_reason=root_reason,
        causes=(),
    )


def _gather_cascade_candidates(
    *,
    own_cursor_type: str | None,
    upstream_keys: tuple[CompiledObjectKey, ...],
    effective_cascades: dict[str, CascadeResult],
    model_cursor_types: dict[str, str | None],
) -> list[CascadeCause]:
    """Gather upstream effective backfills that can cascade to this model."""

    candidates: list[CascadeCause] = []
    key: CompiledObjectKey
    for key in upstream_keys:
        if key.resource_type not in (CompiledResourceType.MODEL, CompiledResourceType.FUNCTION):
            continue
        upstream_cascade: CascadeResult | None = effective_cascades.get(key.name)
        if upstream_cascade is None:
            continue
        if upstream_cascade.effective_action == BackfillAction.WARN_ONLY:
            continue

        if key.resource_type == CompiledResourceType.FUNCTION:
            candidates.append(
                CascadeCause(
                    model_name=key.name,
                    effective_action=upstream_cascade.effective_action,
                    effective_duration=upstream_cascade.effective_duration,
                    root_cause=upstream_cascade.root_cause or key.name,
                    root_reason=upstream_cascade.root_reason,
                )
            )
            continue

        upstream_cursor_type: str | None = model_cursor_types.get(key.name)
        same_cursor_type: bool = (
            own_cursor_type is not None
            and upstream_cursor_type is not None
            and own_cursor_type == upstream_cursor_type
        )

        if upstream_cascade.effective_action == BackfillAction.FULL:
            candidates.append(
                CascadeCause(
                    model_name=key.name,
                    effective_action=upstream_cascade.effective_action,
                    effective_duration=upstream_cascade.effective_duration,
                    root_cause=upstream_cascade.root_cause or key.name,
                    root_reason=upstream_cascade.root_reason,
                )
            )
        elif same_cursor_type:
            candidates.append(
                CascadeCause(
                    model_name=key.name,
                    effective_action=upstream_cascade.effective_action,
                    effective_duration=upstream_cascade.effective_duration,
                    root_cause=upstream_cascade.root_cause or key.name,
                    root_reason=upstream_cascade.root_reason,
                )
            )

    return candidates


def _pick_winner(
    *,
    candidates: list[CascadeCause],
    own_backfill: BackfillResult,
) -> CascadeCause | None:
    """Pick the candidate that exceeds the model's own backfill.

    Returns the most aggressive candidate, or None if no candidate exceeds the
    model's own backfill. Among tied candidates, picks alphabetically by model
    name.
    """

    own_rank: tuple[int, int] = _backfill_rank(own_backfill.action, own_backfill.duration)

    best: CascadeCause | None = None
    best_rank: tuple[int, int] = own_rank

    candidate: CascadeCause
    for candidate in candidates:
        candidate_rank: tuple[int, int] = _backfill_rank(
            candidate.effective_action, candidate.effective_duration
        )
        if candidate_rank > best_rank:
            best = candidate
            best_rank = candidate_rank
        elif candidate_rank == best_rank and best is not None:
            if candidate.model_name < best.model_name:
                best = candidate

    return best


def _backfill_rank(action: BackfillAction, duration: str | None) -> tuple[int, int]:
    """Produce a comparable rank tuple for a backfill action.

    Returns (action_rank, duration_seconds) where action_rank orders
    WARN_ONLY < BOUNDED < FULL, and duration_seconds orders bounded
    durations by total size.
    """

    action_rank: int = _ACTION_RANK[action]
    duration_seconds: int = 0
    if action == BackfillAction.BOUNDED and duration is not None:
        td: timedelta | None = _parse_duration(duration)
        if td is not None:
            duration_seconds = int(td.total_seconds())
    return (action_rank, duration_seconds)


def _parse_duration(duration: str) -> timedelta | None:
    """Parse a duration string like '1d', '6h', '30m', '15s' into a timedelta."""

    match: re.Match[str] | None = _DURATION_PATTERN.match(duration)
    if match is None:
        return None
    days: int = int(match.group(1) or 0)
    hours: int = int(match.group(2) or 0)
    minutes: int = int(match.group(3) or 0)
    seconds: int = int(match.group(4) or 0)
    if days == 0 and hours == 0 and minutes == 0 and seconds == 0:
        return None
    return timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
