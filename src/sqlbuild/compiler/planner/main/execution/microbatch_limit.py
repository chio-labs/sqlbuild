"""Microbatch planning limit decisions shared by planner and runtime."""

from __future__ import annotations

from sqlbuild.spec.contracts.types import MicrobatchLimitAction


def microbatch_limit_warning(
    *, model_name: str, max_batches: int | None, batch_count: int, action: MicrobatchLimitAction
) -> str | None:
    """Return the prominent warning/error message when one model exceeds its limit."""

    if max_batches is None or batch_count <= max_batches:
        return None
    return (
        f"MICROBATCH LIMIT EXCEEDED: model '{model_name}' planned {batch_count} batches, "
        f"above the per-model limit of {max_batches} (action={action.value}). "
        "Use --max-microbatches with an intentional invocation-specific value for this backfill."
    )
