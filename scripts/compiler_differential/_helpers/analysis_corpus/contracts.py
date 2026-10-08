"""Failure cases owned by the native contracts and promotion conflicts lane."""

from scripts.compiler_differential.models import FailureCase


def contracts_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return ()
