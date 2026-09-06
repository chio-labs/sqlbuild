"""Active compile timing context."""

from contextvars import ContextVar
from typing import ClassVar

from sqlbuild.compiler.profiling.models import CompileTimingCollector


class CompileTimingContext:
    """Own the invocation-local active compile timing collector."""

    active: ClassVar[ContextVar[CompileTimingCollector | None]] = ContextVar(
        "active_compile_timings", default=None
    )
