"""Replay-on-change policy public entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.changes.policy import resolve_replay_on_change as _resolve
from sqlbuild.compiler.planner.models import BackfillResult


def resolve_replay_on_change(*, replay_on_change: str | None) -> BackfillResult:
    """Resolve a configured replay-on-change policy."""

    return _resolve(replay_on_change=replay_on_change)
