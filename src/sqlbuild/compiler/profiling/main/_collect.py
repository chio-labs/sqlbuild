"""Compile timing collection entry point."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import Token

from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector


@contextmanager
def collect_compile_timings() -> Iterator[CompileTimingCollector]:
    """Collect detailed timings for one compile command invocation."""

    collector: CompileTimingCollector = CompileTimingCollector()
    token: Token[CompileTimingCollector | None] = CompileTimingContext.active.set(collector)
    try:
        yield collector
    finally:
        CompileTimingContext.active.reset(token)
