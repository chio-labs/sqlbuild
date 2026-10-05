"""Public entry for the compile reuse counters reported in compile_timings."""

from __future__ import annotations

from sqlbuild.cli.compile_reuse._helpers.timings import reuse_timings
from sqlbuild.cli.compile_reuse.models import CompileReuseAttempt


def compile_reuse_timings(*, attempt: CompileReuseAttempt) -> dict[str, int]:
    """Return the hit, miss, and bypass counters plus the time spent checking for reuse."""

    return reuse_timings(outcome=attempt.outcome, check_ms=attempt.check_ms)
