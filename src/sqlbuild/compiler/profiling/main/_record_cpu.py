"""Compile phase CPU recording entry point."""

import time
from contextlib import AbstractContextManager

from sqlbuild.compiler.profiling._helpers.timing import recorded_timing
from sqlbuild.compiler.profiling.types import CompileTimingPhase


def record_compile_cpu_timing(phase: CompileTimingPhase) -> AbstractContextManager[None]:
    """Record the process CPU time an operation spans, including its worker threads."""

    return recorded_timing(phase=phase, clock=time.process_time_ns)
