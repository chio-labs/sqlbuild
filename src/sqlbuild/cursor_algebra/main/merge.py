"""Merge typed cursor intervals."""

from sqlbuild.cursor_algebra._helpers.intervals import merge_interval_values
from sqlbuild.cursor_algebra.models import AlignedInterval


def merge(*, intervals: tuple[AlignedInterval, ...]) -> tuple[AlignedInterval, ...]:
    """Merge overlapping or adjacent canonical intervals."""

    return merge_interval_values(intervals=intervals)
