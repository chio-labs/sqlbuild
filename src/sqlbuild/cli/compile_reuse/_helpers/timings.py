"""Compile reuse counters and elapsed time reported in compile_timings."""

from __future__ import annotations

import time

from sqlbuild.cli.compile_reuse.constants import (
    MILLISECONDS_PER_SECOND,
    REUSE_BYPASS_TIMING,
    REUSE_CHECK_TIMING,
    REUSE_HIT_TIMING,
    REUSE_MISS_TIMING,
)
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome


def reuse_timings(*, outcome: CompileReuseOutcome, check_ms: int) -> dict[str, int]:
    """Return the reuse counters and check time reported in compile_timings."""

    return {
        REUSE_HIT_TIMING: int(outcome is CompileReuseOutcome.HIT),
        REUSE_MISS_TIMING: int(outcome is CompileReuseOutcome.MISS),
        REUSE_BYPASS_TIMING: int(outcome is CompileReuseOutcome.BYPASS),
        REUSE_CHECK_TIMING: check_ms,
    }


def elapsed_ms(*, started: float) -> int:
    """Return whole milliseconds elapsed since a monotonic start time."""

    return int((time.monotonic() - started) * MILLISECONDS_PER_SECOND)
