"""Canonical cursor grain metadata."""

from sqlbuild.compiler.planner.types import CursorGrain

GRAIN_ORDER: dict[CursorGrain, int] = {
    CursorGrain.SECOND: 0,
    CursorGrain.MINUTE: 1,
    CursorGrain.HOUR: 2,
    CursorGrain.DAY: 3,
    CursorGrain.MONTH: 4,
    CursorGrain.YEAR: 5,
}

GRAIN_BATCH_SIZE: dict[CursorGrain, str] = {
    CursorGrain.SECOND: "1s",
    CursorGrain.MINUTE: "1m",
    CursorGrain.HOUR: "1h",
    CursorGrain.DAY: "1d",
    CursorGrain.MONTH: "1mo",
    CursorGrain.YEAR: "1y",
}

DURATION_YEAR_UNIT: str = "y"
DURATION_MONTH_UNIT: str = "mo"
DURATION_DAY_UNIT: str = "d"
DURATION_HOUR_UNIT: str = "h"
DURATION_MINUTE_UNIT: str = "m"
DURATION_SECOND_UNIT: str = "s"

MINUTE_TO_DAY_DURATION_UNITS: frozenset[str] = frozenset(
    {DURATION_MINUTE_UNIT, DURATION_HOUR_UNIT, DURATION_DAY_UNIT}
)
