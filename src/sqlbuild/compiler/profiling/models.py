"""Compile profiling models."""

from dataclasses import dataclass, field

from sqlbuild.compiler.profiling.constants import COMPILE_METRICS, COMPILE_TIMING_PHASES
from sqlbuild.compiler.profiling.types import CompileMetric, CompileTimingPhase


@dataclass(frozen=True)
class CompileTimingCollector:
    """Accumulate elapsed nanoseconds for nested compile operations."""

    elapsed_ns: dict[CompileTimingPhase, int] = field(default_factory=dict)
    metrics: dict[CompileMetric, int] = field(default_factory=dict)

    def add(self, *, phase: CompileTimingPhase, elapsed_ns: int) -> None:
        """Add one measured operation to a compile phase."""

        self.elapsed_ns[phase] = self.elapsed_ns.get(phase, 0) + elapsed_ns

    def add_metric(self, *, metric: CompileMetric, value: int) -> None:
        """Add a non-negative compile metric to the current invocation."""

        self.metrics[metric] = self.metrics.get(metric, 0) + value

    def as_milliseconds(self) -> dict[str, int]:
        """Return every supported phase in stable presentation order."""

        return {
            phase: self.elapsed_ns.get(phase, 0) // 1_000_000 for phase in COMPILE_TIMING_PHASES
        } | {metric: self.metrics.get(metric, 0) for metric in COMPILE_METRICS}
