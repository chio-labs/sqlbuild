"""Failure cases owned by the native semantic completion lane."""

from scripts.compiler_differential.models import FailureCase


def semantic_checks_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return ()
