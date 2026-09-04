"""Microbatch planning limit decisions shared by planner and runtime."""

from collections.abc import Mapping
from typing import cast

from sqlbuild.spec.contracts.types import MicrobatchLimitAction


def _resolve_microbatch_limit_config(
    *, values: Mapping[str, object]
) -> tuple[int | None, MicrobatchLimitAction | None]:
    """Return the configured limit and explicit action from validated model values."""

    raw: object | None = values.get("microbatch_limit")
    if isinstance(raw, dict):
        raw_config: Mapping[str, object] = cast("Mapping[str, object]", raw)
        max_batches: object | None = raw_config.get("max_batches")
        action: object | None = raw_config.get("action")
        if (
            isinstance(max_batches, int)
            and not isinstance(max_batches, bool)
            and max_batches > 0
            and isinstance(action, str)
        ):
            return max_batches, MicrobatchLimitAction(action)
    legacy_limit: object | None = values.get("max_microbatches")
    return (
        legacy_limit
        if isinstance(legacy_limit, int) and not isinstance(legacy_limit, bool) and legacy_limit > 0
        else None,
        None,
    )


def microbatch_limit_warning(
    *, model_name: str, max_batches: int | None, batch_count: int, action: MicrobatchLimitAction
) -> str | None:
    """Return the prominent warning/error message when one model exceeds its limit."""

    if max_batches is None or batch_count <= max_batches:
        return None
    return (
        f"MICROBATCH LIMIT EXCEEDED: model '{model_name}' planned {batch_count} batches, "
        f"above the per-model limit of {max_batches} (action={action.value}). "
        + (
            f"Selected {max_batches} batches and deferred {batch_count - max_batches}."
            if action
            in {
                MicrobatchLimitAction.CAP_FROM_END,
                MicrobatchLimitAction.CAP_FROM_START,
            }
            else (
                "Use --max-microbatches with an intentional invocation-specific value for "
                "this backfill."
            )
        )
    )
