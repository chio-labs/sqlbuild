"""Derive availability from an observed cursor maximum."""

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra._helpers.intervals import observed_partition_value
from sqlbuild.cursor_algebra.types import CursorScalar


def exclusive_end_from_observed_max(
    *, value: CursorScalar, grain: CursorGrain | None
) -> CursorScalar:
    """Convert an observed maximum to its partition's exclusive end."""

    return observed_partition_value(value=value, grain=grain).end
