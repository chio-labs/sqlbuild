"""Compile phase recording entry point."""

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.compiler.profiling.types import CompileTimingPhase


@contextmanager
def record_compile_timing(phase: CompileTimingPhase) -> Iterator[None]:
    """Record an operation when a compile timing collector is active."""

    collector: CompileTimingCollector | None = CompileTimingContext.active.get()
    if collector is None:
        yield
        return
    start_ns: int = time.perf_counter_ns()
    try:
        yield
    finally:
        collector.add(phase=phase, elapsed_ns=time.perf_counter_ns() - start_ns)
