"""Published cursor replay-policy operation."""

from sqlbuild.compiler.planner._helpers.resolve.cursor import (
    apply_cursor_replay_policy as _apply_cursor_replay_policy,
)


def apply_cursor_replay_policy(
    *,
    start: str,
    end: str,
    cursor_start: str | None,
    cursor_type: str | None,
    lookback: str | None,
    backfill_duration: str | None,
    has_start_override: bool,
) -> str:
    """Apply replay, lookback, and configured lower-bound policy to a cursor start."""

    return _apply_cursor_replay_policy(
        start=start,
        end=end,
        cursor_start=cursor_start,
        cursor_type=cursor_type,
        lookback=lookback,
        backfill_duration=backfill_duration,
        has_start_override=has_start_override,
    )
