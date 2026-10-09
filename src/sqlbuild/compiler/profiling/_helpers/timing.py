"""Compile phase timing by a chosen clock."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager

from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.compiler.profiling.types import CompileTimingPhase


@contextmanager
def recorded_timing(*, phase: CompileTimingPhase, clock: Callable[[], int]) -> Iterator[None]:
    """Record an operation by `clock` when a compile timing collector is active."""

    collector: CompileTimingCollector | None = CompileTimingContext.active.get()
    if collector is None:
        yield
        return
    start_ns: int = clock()
    try:
        yield
    finally:
        collector.add(phase=phase, elapsed_ns=clock() - start_ns)
