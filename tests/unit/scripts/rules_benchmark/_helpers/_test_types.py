"""Test-case models for required-CI Rules guards."""

from dataclasses import dataclass

from scripts.rules_benchmark.models import BenchmarkResult


@dataclass(frozen=True)
class CacheGuardTestCase:
    description: str
    results: tuple[BenchmarkResult, ...]
    expected_failures: tuple[str, ...]


@dataclass(frozen=True)
class ResourceGuardTestCase:
    description: str
    cache_bytes: int
    results: tuple[BenchmarkResult, ...]
    expected_failures: tuple[str, ...]


@dataclass(frozen=True)
class WarmIterationsTestCase:
    description: str
    model_count: int
    rule_count: int
    expected_iterations: int
