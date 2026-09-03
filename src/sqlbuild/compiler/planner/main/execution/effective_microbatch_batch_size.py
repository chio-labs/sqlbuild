"""Resolve the effective microbatch size after cursor-grain propagation."""

from __future__ import annotations

from sqlbuild.compiler.planner.constants import CURSOR_GRAIN_BATCH_SIZE
from sqlbuild.spec.contracts.constants import EFFECTIVE_BATCH_SIZE_TOKEN


def resolve_effective_microbatch_batch_size(*, batch_size: str, effective_grain: str) -> str:
    """Resolve the explicit effective batch-size token against the replay grain."""

    if batch_size != EFFECTIVE_BATCH_SIZE_TOKEN:
        return batch_size
    return CURSOR_GRAIN_BATCH_SIZE[effective_grain]
