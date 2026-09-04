"""Convert an inclusive cursor bound to an exclusive bound."""

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.intervals import shift_inclusive_bound
from sqlbuild.cursor_algebra.types import CursorScalar


def inclusive_to_exclusive(*, value: CursorScalar, grain: CursorGrain | None) -> CursorScalar:
    """Advance an operator-declared inclusive bound by one cursor unit."""

    return shift_inclusive_bound(value=value, grain=grain, direction=1)
