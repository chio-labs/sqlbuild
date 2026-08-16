"""Resolve the effective microbatch size after cursor-grain propagation."""

from __future__ import annotations

from sqlbuild.compiler.planner.constants import CURSOR_GRAIN_BATCH_SIZE, CURSOR_GRAIN_ORDER
from sqlbuild.compiler.planner.models import Duration
from sqlbuild.compiler.planner.types import CursorGrain


def resolve_effective_microbatch_batch_size(*, batch_size: str, effective_grain: str) -> str:
    """Coarsen a batch only when its largest declared unit is finer than the grain."""

    duration: Duration | None = Duration.parse(batch_size)
    if duration is None:
        return batch_size
    batch_order: int = _duration_order(duration=duration)
    if batch_order >= CURSOR_GRAIN_ORDER[effective_grain]:
        return batch_size
    return CURSOR_GRAIN_BATCH_SIZE[effective_grain]


def _duration_order(*, duration: Duration) -> int:
    if duration.years > 0:
        return CURSOR_GRAIN_ORDER[CursorGrain.YEAR]
    if duration.months > 0:
        return CURSOR_GRAIN_ORDER[CursorGrain.MONTH]
    if duration.days > 0:
        return CURSOR_GRAIN_ORDER[CursorGrain.DAY]
    if duration.hours > 0:
        return CURSOR_GRAIN_ORDER[CursorGrain.HOUR]
    if duration.minutes > 0:
        return CURSOR_GRAIN_ORDER[CursorGrain.MINUTE]
    return CURSOR_GRAIN_ORDER[CursorGrain.SECOND]
