"""Select the maximum typed cursor bound."""

from sqlbuild.cursor_algebra._helpers.comparison import as_scalar, comparison_value


def max_bound[T](*, values: tuple[T, ...] | list[T], cursor_type: str) -> T:
    """Select the numerically or temporally largest raw bound."""

    return max(
        values,
        key=lambda raw: comparison_value(value=as_scalar(raw=raw, cursor_type=cursor_type)),
    )
