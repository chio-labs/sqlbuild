"""Clamp a typed cursor interval."""

from sqlbuild.cursor_algebra._helpers.intervals import clamp_interval
from sqlbuild.cursor_algebra.models import AlignedInterval


def clamp(*, interval: AlignedInterval, bounds: AlignedInterval) -> AlignedInterval | None:
    """Intersect two compatible half-open intervals."""

    return clamp_interval(interval=interval, bounds=bounds)
