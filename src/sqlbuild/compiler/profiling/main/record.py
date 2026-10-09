"""Compile phase recording entry point."""

import time
from contextlib import AbstractContextManager

from sqlbuild.compiler.profiling._helpers.timing import recorded_timing
from sqlbuild.compiler.profiling.types import CompileTimingPhase


def record_compile_timing(phase: CompileTimingPhase) -> AbstractContextManager[None]:
    """Record an operation when a compile timing collector is active."""

    return recorded_timing(phase=phase, clock=time.perf_counter_ns)
