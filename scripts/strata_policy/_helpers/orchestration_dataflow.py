"""Orchestration dataflow predicates for SQLBuild custom rules."""

from scripts.strata_policy.constants import (
    DISCARDED_CALL_ALLOWED_NAMES,
    DISCARDED_CALL_ALLOWED_PREFIXES,
)


def discarded_call_name_is_allowed(*, name: str) -> bool:
    """Return whether a discarded bare call has an approved side-effect name."""

    normalized_name: str = name.lstrip("_")
    return normalized_name in DISCARDED_CALL_ALLOWED_NAMES or normalized_name.startswith(
        DISCARDED_CALL_ALLOWED_PREFIXES
    )
