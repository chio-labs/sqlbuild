"""Cap typed cursor intervals from the start."""


def cap_from_start[T](*, intervals: tuple[T, ...], count: int) -> tuple[T, ...]:
    """Select at most count intervals from the start."""

    return intervals[: max(count, 0)]
