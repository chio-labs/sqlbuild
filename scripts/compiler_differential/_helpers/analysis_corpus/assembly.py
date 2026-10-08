"""Failure cases owned by the native project assembly and target validation lane."""

from scripts.compiler_differential.models import FailureCase


def assembly_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return ()
