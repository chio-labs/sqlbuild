"""Public maximum automatic-start safety entry points."""

from __future__ import annotations

from sqlbuild.compiler.planner._helpers.resolve.maximum_start import (
    apply_maximum_start_policy as _apply_maximum_start_policy,
)
from sqlbuild.compiler.planner.models import (
    CursorBounds,
    MaximumStartPolicyInputs,
    ModelCursorSnapshot,
)


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
    """Apply maximum automatic-start safety to cursor bounds."""

    return _apply_maximum_start_policy(
        bounds=bounds,
        snapshot=snapshot,
        cursor_type=cursor_type,
        cursor_grain=cursor_grain,
        cursor_start=cursor_start,
        lookback=lookback,
        backfill_duration=backfill_duration,
        policy=policy,
        has_start_override=has_start_override,
    )
