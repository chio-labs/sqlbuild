"""Cap typed cursor intervals from the end."""

from sqlbuild.cursor_algebra.models import AlignedInterval


def cap_from_end(
    *, intervals: tuple[AlignedInterval, ...], count: int
) -> tuple[AlignedInterval, ...]:
    """Select at most count intervals from the end."""

    return intervals[-max(count, 0) :] if count > 0 else ()
