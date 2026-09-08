"""Structured Project Policy benchmark results."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkResult:
    """Measurements and counters for one benchmark scenario."""

    scenario: str
    seconds: tuple[float, ...]
    evaluated_models: int
    cache_hits: int
    cache_misses: int
    rejected: bool = False
