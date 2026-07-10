"""Replay-on-change policy resolution."""

from __future__ import annotations

import re

from sqlbuild.compiler.planner.models import BackfillResult
from sqlbuild.compiler.planner.types import BackfillAction

_BOUNDED_PATTERN: re.Pattern[str] = re.compile(r"^bounded-(.+)$")

_ACTION_PRIORITY: dict[BackfillAction, int] = {
    BackfillAction.FORWARD_ONLY: 0,
    BackfillAction.BOUNDED: 1,
    BackfillAction.FULL: 2,
}


def resolve_replay_on_change(
    *,
    replay_on_change: str | None,
) -> BackfillResult:
    """Resolve replay behavior for a detected model version change."""

    return _resolve_replay_value(replay_on_change)


def pick_more_aggressive(a: BackfillResult, *, b: BackfillResult) -> BackfillResult:
    """Return the more aggressive of two backfill results."""

    if _ACTION_PRIORITY[a.action] >= _ACTION_PRIORITY[b.action]:
        return a
    return b


def _resolve_replay_value(raw: str | None) -> BackfillResult:
    """Parse a raw replay policy value into a BackfillResult."""

    if raw is None or raw == BackfillAction.FORWARD_ONLY:
        return BackfillResult(action=BackfillAction.FORWARD_ONLY)
    if raw == BackfillAction.FULL:
        return BackfillResult(action=BackfillAction.FULL)
    match: re.Match[str] | None = _BOUNDED_PATTERN.match(raw)
    if match is not None:
        duration: str = match.group(1).strip()
        return BackfillResult(action=BackfillAction.BOUNDED, duration=duration)
    return BackfillResult(action=BackfillAction.FORWARD_ONLY)
