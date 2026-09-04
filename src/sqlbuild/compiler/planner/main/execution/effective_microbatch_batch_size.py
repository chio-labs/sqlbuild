"""Resolve the effective microbatch size after cursor-grain propagation."""

from __future__ import annotations

from sqlbuild.compiler.planner.types import CursorGrain
from sqlbuild.cursor_algebra.constants import GRAIN_BATCH_SIZE
from sqlbuild.spec.contracts.constants import EFFECTIVE_BATCH_SIZE_TOKEN


def resolve_effective_microbatch_batch_size(*, batch_size: str, effective_grain: str) -> str:
    """Resolve the explicit effective batch-size token against the replay grain."""

    if batch_size != EFFECTIVE_BATCH_SIZE_TOKEN:
        return batch_size
    return GRAIN_BATCH_SIZE[CursorGrain(effective_grain)]
