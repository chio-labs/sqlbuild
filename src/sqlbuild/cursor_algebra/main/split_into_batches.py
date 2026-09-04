"""Split a typed cursor interval into batches."""

from sqlbuild.cursor_algebra._helpers.intervals import split_interval
from sqlbuild.cursor_algebra.models import AlignedInterval


def split_into_batches(*, interval: AlignedInterval, step: int) -> tuple[AlignedInterval, ...]:
    """Split an interval into batches of a positive number of grain units."""

    return split_interval(interval=interval, step=step)
