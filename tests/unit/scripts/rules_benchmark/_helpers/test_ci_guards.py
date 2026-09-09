"""Tests for required-CI Rules performance guards."""

from scripts.rules_benchmark._helpers.workflow import (
    _ci_cache_guard_failures,
    _ci_resource_guard_failures,
)
from scripts.rules_benchmark.models import BenchmarkResult


def test_given_exact_invalidation_counts_when_checking_ci_cache_guards_then_passes() -> None:
    results = (
        _result(scenario="unchanged_warm", hits=100_002, misses=0),
        _result(scenario="multi_model_edit", hits=99_000, misses=1_002),
        _result(scenario="sql_test_edit", hits=90_000, misses=10_002),
        _result(scenario="macro_edit", hits=99_900, misses=102),
        _result(scenario="project_config_edit", hits=2_020, misses=97_982),
        _result(scenario="custom_rule_helper_edit", hits=95_001, misses=5_001),
        _result(scenario="custom_rule_source_edit", hits=95_001, misses=5_001),
    )

    failures = _ci_cache_guard_failures(model_count=5000, rule_count=20, results=results)

    assert failures == ()


def test_given_changed_invalidation_count_when_checking_ci_cache_guards_then_fails() -> None:
    results = (_result(scenario="unchanged_warm", hits=100_001, misses=1),)

    failures = _ci_cache_guard_failures(model_count=5000, rule_count=20, results=results)

    assert failures == (
        "5000 models / 20 Rules / unchanged_warm sample 1: expected cache 100002/0, got 100001/1",
    )


def test_given_result_over_reviewed_limit_when_checking_resource_guards_then_fails() -> None:
    results = (
        BenchmarkResult(
            scenario="unchanged_warm",
            seconds=(12.0,),
            evaluated_models=5000,
            cache_hits=100_002,
            cache_misses=0,
            peak_rss_bytes=(901_000_000,),
        ),
    )

    failures = _ci_resource_guard_failures(
        model_count=5000,
        rule_count=20,
        cache_bytes=35_000_001,
        results=results,
    )

    assert failures == (
        "5000 models / 20 Rules cache uses 35000001 bytes, above 35000000",
        "5000 models / 20 Rules scenario contract differs: expected "
        "['cold', 'custom_rule_helper_edit', 'custom_rule_source_edit', 'macro_edit', "
        "'multi_model_edit', 'project_config_edit', 'rules_cold', 'sql_test_edit', "
        "'unchanged_warm'], got ['unchanged_warm']",
        "5000 models / 20 Rules / unchanged_warm took 12.00s, above 11s",
        "5000 models / 20 Rules / unchanged_warm used 901000000 peak RSS bytes, above 900000000",
    )


def _result(*, scenario: str, hits: int, misses: int) -> BenchmarkResult:
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


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-vv"]))
