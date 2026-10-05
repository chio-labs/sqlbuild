"""Locate and replace the compile_timings object inside a stored JSON report."""

from __future__ import annotations

import json
import time

from sqlbuild.cli.compile_reuse.constants import (
    COMPILE_TIMINGS_CLOSING,
    COMPILE_TIMINGS_OPENING,
    JSON_OBJECT_OPENING,
    MILLISECONDS_PER_SECOND,
    REUSE_BYPASS_TIMING,
    REUSE_CHECK_TIMING,
    REUSE_HIT_TIMING,
    REUSE_MISS_TIMING,
)
from sqlbuild.cli.compile_reuse.types import CompileReuseOutcome


def compile_timings_span(*, stdout: str) -> tuple[int, int] | None:
    """Return the character span of the top-level compile_timings object, if any."""

    opening: int = stdout.find(COMPILE_TIMINGS_OPENING)
    if opening < 0:
        return None
    start: int = opening + len(COMPILE_TIMINGS_OPENING) - 1
    closing: int = stdout.find(COMPILE_TIMINGS_CLOSING, start)
    if closing < 0 or JSON_OBJECT_OPENING in stdout[start + 1 : closing]:
        return None
    return start, closing + len(COMPILE_TIMINGS_CLOSING)


def replace_compile_timings(*, stdout: str, span: tuple[int, int], timings: dict[str, int]) -> str:
    """Splice freshly measured timings into a stored two-space-indented JSON report."""

    rendered: str = (
        "{\n"
        + ",\n".join(f"    {json.dumps(name)}: {value}" for name, value in timings.items())
        + COMPILE_TIMINGS_CLOSING
    )
    return stdout[: span[0]] + rendered + stdout[span[1] :]


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
