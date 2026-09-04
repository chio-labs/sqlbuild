"""Cap typed cursor intervals from the start."""

from sqlbuild.cursor_algebra.models import AlignedInterval


def cap_from_start(
    *, intervals: tuple[AlignedInterval, ...], count: int
) -> tuple[AlignedInterval, ...]:
    """Select at most count intervals from the start."""

    return intervals[: max(count, 0)]
