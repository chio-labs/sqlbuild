"""Advance a typed cursor boundary."""

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.arithmetic import advance_scalar
from sqlbuild.cursor_algebra.types import CursorScalar


def next_boundary(*, value: CursorScalar, grain: CursorGrain) -> CursorScalar:
    """Return the boundary one grain after an aligned cursor value."""

    return advance_scalar(value=value, grain=grain)
