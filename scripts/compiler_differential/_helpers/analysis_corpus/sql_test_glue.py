"""Failure cases owned by the native SQL-test planning glue lane."""

from scripts.compiler_differential.models import FailureCase


def sql_test_glue_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return ()
