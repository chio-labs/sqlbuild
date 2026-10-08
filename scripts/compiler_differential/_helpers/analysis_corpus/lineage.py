"""Failure cases owned by the native FAST lineage facts lane."""

from scripts.compiler_differential.models import FailureCase


def lineage_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return ()
