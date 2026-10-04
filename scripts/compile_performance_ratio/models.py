"""Typed records for same-runner compile performance comparisons."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompileRun:
    label: str
    wall_seconds: float
    cpu_seconds: float
    timings_ms: dict[str, int]
    analysis_cache_misses: int | None = None


@dataclass(frozen=True)
class CompileComparison:
    kind: str
    models: int
    mode: str
    base_wall_seconds: float
    head_wall_seconds: float
    base_cpu_seconds: float
    head_cpu_seconds: float
    base_timings_ms: dict[str, float]
    head_timings_ms: dict[str, float]

    @property
    def wall_ratio(self) -> float:
        if self.base_wall_seconds <= 0:
            return float("inf")
        return self.head_wall_seconds / self.base_wall_seconds

    @property
    def cpu_ratio(self) -> float:
        if self.base_cpu_seconds <= 0:
            return float("inf")
        return self.head_cpu_seconds / self.base_cpu_seconds
