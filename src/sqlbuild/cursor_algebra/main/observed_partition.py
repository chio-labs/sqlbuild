"""Build the partition containing an observed cursor value."""

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.intervals import observed_partition_value
from sqlbuild.cursor_algebra.models import AlignedInterval
from sqlbuild.cursor_algebra.types import CursorScalar


def observed_partition(*, value: CursorScalar, grain: CursorGrain | None) -> AlignedInterval:
    """Return the canonical partition containing an observed physical value."""

    return observed_partition_value(value=value, grain=grain)
