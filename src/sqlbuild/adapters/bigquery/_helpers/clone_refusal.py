"""Recognize BigQuery refusals to clone a table where a physical copy can still succeed."""

from __future__ import annotations

from sqlbuild.adapters.bigquery.constants import (
    CLONE_REFUSAL_ERROR_CODE,
    CLONE_REFUSAL_PHRASES,
    CLONE_REFUSAL_REASONS,
    MAX_CLONE_REFUSAL_ERROR_CHAIN,
)


def is_bigquery_clone_refusal(error: BaseException) -> bool:
    """Return whether a driver error in the cause chain is a clone-capability refusal."""

    current: BaseException | None = error
    depth: int = 0
    while current is not None and depth < MAX_CLONE_REFUSAL_ERROR_CHAIN:
        if _is_refusal(current):
            return True
        current = current.__cause__ or current.__context__
        depth += 1
    return False


def _is_refusal(error: BaseException) -> bool:
    details: object | None = getattr(error, "errors", None)
    if getattr(error, "code", None) != CLONE_REFUSAL_ERROR_CODE or not isinstance(details, list):
        return False
    reasons: set[str] = {
        str(detail.get("reason", "")) for detail in details if isinstance(detail, dict)
    }
    messages: str = " ".join(
        str(detail.get("message", "")) for detail in details if isinstance(detail, dict)
    ).lower()
    return (
        bool(reasons)
        and reasons <= CLONE_REFUSAL_REASONS
        and any(phrase in messages for phrase in CLONE_REFUSAL_PHRASES)
    )
