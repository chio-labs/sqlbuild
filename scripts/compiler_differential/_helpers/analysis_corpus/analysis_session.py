"""Failure cases owned by the native model analysis session lane."""

from scripts.compiler_differential.models import FailureCase


def analysis_session_failure_cases() -> tuple[FailureCase, ...]:
    """Return this lane's failure cases; the lane appends here without editing shared lists."""

    return ()
