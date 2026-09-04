"""Cap typed cursor intervals from the end."""


def cap_from_end[T](*, intervals: tuple[T, ...], count: int) -> tuple[T, ...]:
    """Select at most count intervals from the end."""

    return intervals[-max(count, 0) :] if count > 0 else ()
