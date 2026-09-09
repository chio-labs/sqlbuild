"""Helpers for required-CI Rules guard tests."""

from scripts.rules_benchmark.models import BenchmarkResult


def benchmark_result(*, scenario: str, hits: int, misses: int) -> BenchmarkResult:
    return BenchmarkResult(
        scenario=scenario,
        seconds=(1.0,),
        evaluated_models=5000,
        cache_hits=hits,
        cache_misses=misses,
        cache_hit_samples=(hits,),
        cache_miss_samples=(misses,),
        peak_rss_bytes=(1,),
    )
