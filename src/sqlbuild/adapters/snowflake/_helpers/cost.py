"""Describe Snowflake cost-collection failures."""

from __future__ import annotations

_FAILURE_DETAIL_LIMIT: int = 200


def cost_failure_cause(error: Exception) -> str:
    """Name a cost-collection failure by type and its message on one bounded line."""

    detail: str = " ".join(str(error).split())
    if not detail:
        return type(error).__name__
    if len(detail) > _FAILURE_DETAIL_LIMIT:
        detail = f"{detail[: _FAILURE_DETAIL_LIMIT - 3]}..."
    return f"{type(error).__name__}: {detail}"
