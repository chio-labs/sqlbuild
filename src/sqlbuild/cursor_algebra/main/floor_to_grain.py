"""Floor a typed cursor scalar."""

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.arithmetic import floor_scalar
from sqlbuild.cursor_algebra.types import CursorScalar


def floor_to_grain(*, value: CursorScalar, grain: CursorGrain) -> CursorScalar:
    """Return the aligned boundary at or before a cursor value."""

    return floor_scalar(value=value, grain=grain)
