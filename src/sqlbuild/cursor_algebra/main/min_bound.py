"""Select the minimum typed cursor bound."""

from sqlbuild.cursor_algebra._helpers.comparison import as_scalar, comparison_value


def min_bound[T](*, values: tuple[T, ...] | list[T], cursor_type: str) -> T:
    """Select the numerically or temporally smallest raw bound."""

    return min(
        values,
        key=lambda raw: comparison_value(value=as_scalar(raw=raw, cursor_type=cursor_type)),
    )
