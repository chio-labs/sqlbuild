"""Public typed cursor replay policy entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    apply_typed_cursor_replay_policy as _apply_typed_cursor_replay_policy,
)
from sqlbuild.compiler.planner.models import Duration
from sqlbuild.cursor_algebra.types import CursorScalar


def apply_typed_cursor_replay_policy(
    *,
    start: CursorScalar,
    end: CursorScalar,
    cursor_start: CursorScalar | str | None,
    cursor_type: str | None,
    lookback: Duration | str | None,
    backfill_duration: Duration | str | None,
    has_start_override: bool,
) -> CursorScalar:
    """Apply replay policy without crossing a string serialization boundary."""

    return _apply_typed_cursor_replay_policy(
        start=start,
        end=end,
        cursor_start=cursor_start,
        cursor_type=cursor_type,
        lookback=lookback,
        backfill_duration=backfill_duration,
        has_start_override=has_start_override,
    )
