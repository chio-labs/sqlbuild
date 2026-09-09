"""Structured Rules benchmark results."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkResult:
    """Measurements and counters for one benchmark scenario."""

    scenario: str
    seconds: tuple[float, ...]
    evaluated_models: int
    cache_hits: int
    cache_misses: int
    core_ms: tuple[int, ...] = ()
    built_in_rules_ms: tuple[int, ...] = ()
    custom_rules_ms: tuple[int, ...] = ()
    rejected: bool = False
