"""Internal compile metric recording entry point."""

from sqlbuild.compiler.profiling.classes.context import CompileTimingContext
from sqlbuild.compiler.profiling.models import CompileTimingCollector
from sqlbuild.compiler.profiling.types import CompileMetric


def record_compile_metric(*, metric: CompileMetric, value: int) -> None:
    """Record one non-negative metric when a compile collector is active."""

    collector: CompileTimingCollector | None = CompileTimingContext.active.get()
    if collector is not None:
        collector.add_metric(metric=metric, value=max(0, value))
