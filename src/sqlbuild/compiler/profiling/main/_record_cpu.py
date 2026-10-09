"""Compile phase CPU recording entry point."""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.compiler.profiling.types import CompileTimingPhase


@contextmanager
def record_compile_cpu_timing(phase: CompileTimingPhase) -> Iterator[None]:
    """Record the process CPU time an operation spans, including its worker threads."""

    collector: CompileTimingCollector | None = CompileTimingContext.active.get()
    if collector is None:
        yield
        return
    start_ns: int = time.process_time_ns()
    try:
        yield
    finally:
        collector.add(phase=phase, elapsed_ns=time.process_time_ns() - start_ns)
