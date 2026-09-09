"""Tests for required-CI Rules performance guards."""

import pytest

from scripts.rules_benchmark._helpers.workflow import (
    _ci_cache_guard_failures,
    _ci_resource_guard_failures,
    _ci_warm_iterations,
)
from scripts.rules_benchmark.models import BenchmarkResult
from tests.unit.scripts.rules_benchmark._helpers._test_types import (
    CacheGuardTestCase,
    ResourceGuardTestCase,
    WarmIterationsTestCase,
)
from tests.unit.scripts.rules_benchmark._helpers.helpers import benchmark_result


@pytest.mark.parametrize(
    "test_case",
    (
        CacheGuardTestCase(
            description="exact invalidation counts",
            results=(
                benchmark_result(scenario="unchanged_warm", hits=100_002, misses=0),
                benchmark_result(scenario="multi_model_edit", hits=99_000, misses=1_002),
                benchmark_result(scenario="sql_test_edit", hits=90_000, misses=10_002),
                benchmark_result(scenario="macro_edit", hits=99_900, misses=102),
                benchmark_result(scenario="project_config_edit", hits=2_020, misses=97_982),
                benchmark_result(scenario="custom_rule_helper_edit", hits=95_001, misses=5_001),
                benchmark_result(scenario="custom_rule_source_edit", hits=95_001, misses=5_001),
            ),
            expected_failures=(),
        ),
        CacheGuardTestCase(
            description="changed unchanged-run count",
            results=(benchmark_result(scenario="unchanged_warm", hits=100_001, misses=1),),
            expected_failures=(
                "5000 models / 20 Rules / unchanged_warm sample 1: expected cache "
                "100002/0, got 100001/1",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_cache_samples_when_checking_ci_guards_then_returns_expected_failures(
    test_case: CacheGuardTestCase,
) -> None:
    failures: tuple[str, ...] = _ci_cache_guard_failures(
        model_count=5000,
        rule_count=20,
        results=test_case.results,
    )

    assert failures == test_case.expected_failures


@pytest.mark.parametrize(
    "test_case",
    (
        ResourceGuardTestCase(
            description="latency memory and cache exceed reviewed limits",
            cache_bytes=17_000_001,
            results=(
                BenchmarkResult(
                    scenario="unchanged_warm",
                    seconds=(8.0, 9.0, 9.0),
                    evaluated_models=5000,
                    cache_hits=100_002,
                    cache_misses=0,
                    peak_rss_bytes=(701_000_000,),
                ),
            ),
            expected_failures=(
                "5000 models / 20 Rules cache uses 17000001 bytes, above 17000000",
                "5000 models / 20 Rules scenario contract differs: expected "
                "['cold', 'custom_rule_helper_edit', 'custom_rule_source_edit', 'macro_edit', "
                "'multi_model_edit', 'project_config_edit', 'rules_cold', 'sql_test_edit', "
                "'unchanged_warm'], got ['unchanged_warm']",
                "5000 models / 20 Rules / unchanged_warm median took 9.00s, above 8.5s",
                "5000 models / 20 Rules / unchanged_warm used 701000000 peak RSS bytes, "
                "above 700000000",
            ),
        ),
        ResourceGuardTestCase(
            description="single warm latency outlier does not fail median guard",
            cache_bytes=1,
            results=(
                BenchmarkResult(
                    scenario="unchanged_warm",
                    seconds=(8.0, 10.0, 8.0),
                    evaluated_models=5000,
                    cache_hits=100_002,
                    cache_misses=0,
                ),
            ),
            expected_failures=(
                "5000 models / 20 Rules scenario contract differs: expected "
                "['cold', 'custom_rule_helper_edit', 'custom_rule_source_edit', 'macro_edit', "
                "'multi_model_edit', 'project_config_edit', 'rules_cold', 'sql_test_edit', "
                "'unchanged_warm'], got ['unchanged_warm']",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_resource_samples_when_checking_ci_guards_then_returns_expected_failures(
    test_case: ResourceGuardTestCase,
) -> None:
    failures: tuple[str, ...] = _ci_resource_guard_failures(
        model_count=5000,
        rule_count=20,
        cache_bytes=test_case.cache_bytes,
        results=test_case.results,
    )

    assert failures == test_case.expected_failures


@pytest.mark.parametrize(
    "test_case",
    (
        WarmIterationsTestCase(
            description="10k 100-Rule stress profile repeats",
            model_count=10_000,
            rule_count=100,
            expected_iterations=3,
        ),
        WarmIterationsTestCase(
            description="10k 20-Rule profile remains single sample",
            model_count=10_000,
            rule_count=20,
            expected_iterations=1,
        ),
        WarmIterationsTestCase(
            description="5k 100-Rule profile remains single sample",
            model_count=5_000,
            rule_count=100,
            expected_iterations=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_ci_profile_when_resolving_warm_iterations_then_returns_expected_count(
    test_case: WarmIterationsTestCase,
) -> None:
    assert (
        _ci_warm_iterations(model_count=test_case.model_count, rule_count=test_case.rule_count)
        == test_case.expected_iterations
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
