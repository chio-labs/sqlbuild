"""Convert an exclusive cursor bound to an inclusive bound."""

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.intervals import shift_inclusive_bound
from sqlbuild.cursor_algebra.types import CursorScalar


def exclusive_to_inclusive(*, value: CursorScalar, grain: CursorGrain | None) -> CursorScalar:
    """Move an exclusive bound back by one configured cursor unit."""

    return shift_inclusive_bound(value=value, grain=grain, direction=-1)
