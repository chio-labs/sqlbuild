"""Public interval-merging entry for causal replay orchestration."""

from __future__ import annotations

from sqlbuild.microbatches._helpers.causal_projection import merge_causal_intervals as _merge
from sqlbuild.microbatches.models import MicrobatchInterval


def merge_causal_intervals(
    *, intervals: tuple[MicrobatchInterval, ...], cursor_type: str
) -> tuple[MicrobatchInterval, ...]:
    """Merge overlapping or adjacent causal intervals while preserving disjoint sets."""

    return _merge(intervals=intervals, cursor_type=cursor_type)
