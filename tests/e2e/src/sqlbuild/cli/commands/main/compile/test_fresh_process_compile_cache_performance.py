"""Fresh-process cache guards for representative semantic projects."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from scripts.cold_compile_performance.main.assert_required_cgroup_memory_limit import (
    assert_required_cgroup_memory_limit,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    FreshProcessCompileCachePerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    FreshProcessCompileBenchmarkResult,
    FreshProcessCompileCacheBenchmarkResult,
    assert_complete_compile_cache_hit,
    assert_successful_compile_cache_payload,
    fresh_process_compile_cache_metrics,
    run_fresh_process_compile_cache_benchmark,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)
_GIB: int = 1024 * 1024 * 1024
_MIB: int = 1024 * 1024
_MAX_WARM_TO_COLD_RATIO: float = 0.70
_MAX_EDIT_TO_COLD_RATIO: float = 0.70
# Writing the cache during a cold compile must stay a small same-runner cost over --no-cache.
_MAX_CACHE_WRITE_CPU_OVERHEAD_RATIO: float = 1.10
_MAX_CACHE_WRITE_WALL_OVERHEAD_RATIO: float = 1.15
_MAX_LARGE_CACHE_WRITE_CPU_OVERHEAD_RATIO: float = 1.15


@pytest.mark.performance
@pytest.mark.cache_compile_performance
@pytest.mark.parametrize(
    "test_case",
    [
        FreshProcessCompileCachePerformanceGuardTestCase(
            description="models_3000_fresh_process_compile_cache_stays_incremental",
            model_count=3_000,
            source_count=713,
            seed_count=141,
            function_count=71,
            macro_count=500,
            test_count=2_945,
            audit_count=5_056,
            expected_cold_max_wall_seconds=22.0,
            expected_warm_max_wall_seconds=11.0,
            expected_edit_max_wall_seconds=11.5,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_edit_to_cold_ratio=_MAX_EDIT_TO_COLD_RATIO,
            expected_max_cache_write_cpu_overhead_ratio=_MAX_CACHE_WRITE_CPU_OVERHEAD_RATIO,
            expected_max_cache_write_wall_overhead_ratio=_MAX_CACHE_WRITE_WALL_OVERHEAD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=96 * _MIB,
            expected_cold_fingerprint=(
                "f96a10c8d9d218c347432118e069f378140bb6f3a852676d968ad9d5f67d2589"
            ),
            expected_leaf_edit_fingerprint=(
                "1e3adee6c9d336de987ea15e3c054726cdf0a00ba8a2b4dcc2f0953b6711cf2c"
            ),
            expected_macro_edit_fingerprint=(
                "81eb4ccff1c67d77a1a4290a239007b92f21bd3112729f64a508592166ed3c39"
            ),
            expected_project_config_fingerprint=(
                "c8fbec90f4c03c1bc8c13478121a2ae4c8b9d7c18b0270102130b689a2e76549"
            ),
            macro_call_interval=6,
            scoped_macros=True,
            expected_macro_edit_misses=1,
        ),
        FreshProcessCompileCachePerformanceGuardTestCase(
            description="models_5000_fresh_process_compile_cache_stays_incremental",
            model_count=5_000,
            source_count=1_189,
            seed_count=236,
            function_count=118,
            macro_count=834,
            test_count=4_908,
            audit_count=8_427,
            expected_cold_max_wall_seconds=35.0,
            expected_warm_max_wall_seconds=18.0,
            expected_edit_max_wall_seconds=18.0,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_edit_to_cold_ratio=_MAX_EDIT_TO_COLD_RATIO,
            expected_max_cache_write_cpu_overhead_ratio=_MAX_CACHE_WRITE_CPU_OVERHEAD_RATIO,
            expected_max_cache_write_wall_overhead_ratio=_MAX_CACHE_WRITE_WALL_OVERHEAD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=160 * _MIB,
            expected_cold_fingerprint=(
                "26de3005daf1b44463b25165238e83c9a8085b00d942eb4beb1b735ce5f09b57"
            ),
            expected_leaf_edit_fingerprint=(
                "e032f1c0edf2e767f356a6af4891c4dcde0d214d6f691ea1dd0336968e97b707"
            ),
            expected_macro_edit_fingerprint=(
                "9e20327a775d2f876f25621d60f8bb81b62d529823a61b8d9686f86de322790c"
            ),
            expected_project_config_fingerprint=(
                "b65db3cfba6cccef479df505832f7e5821f03b7a0b31e8de967b14796644c768"
            ),
            macro_call_interval=6,
            scoped_macros=True,
            expected_macro_edit_misses=1,
        ),
        FreshProcessCompileCachePerformanceGuardTestCase(
            description="models_10000_fresh_process_compile_cache_stays_incremental",
            model_count=10_000,
            source_count=2_377,
            seed_count=471,
            function_count=236,
            macro_count=1_667,
            test_count=9_816,
            audit_count=16_855,
            expected_cold_max_wall_seconds=68.0,
            expected_warm_max_wall_seconds=37.5,
            expected_edit_max_wall_seconds=37.5,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_edit_to_cold_ratio=_MAX_EDIT_TO_COLD_RATIO,
            expected_max_cache_write_cpu_overhead_ratio=_MAX_LARGE_CACHE_WRITE_CPU_OVERHEAD_RATIO,
            expected_max_cache_write_wall_overhead_ratio=_MAX_CACHE_WRITE_WALL_OVERHEAD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=320 * _MIB,
            expected_cold_fingerprint=(
                "b4e5e14d9c1a7ac2e5fc54eac8d1ff2874f2e3042952cb4b80c68c4d4bd1503c"
            ),
            expected_leaf_edit_fingerprint=(
                "fa0b24b685c7f42a14588ab09e7c929332295ecc83cc9adfdc589b4cbc1c6128"
            ),
            expected_macro_edit_fingerprint=(
                "39079f601b624ba4d13d889e9a228c9713ec7ed09ed2127afd3b2c2b48465fbb"
            ),
            expected_project_config_fingerprint=(
                "6dd7ae799420dcb8a49190356a0b97253b59a3106502cc8cf242ee75c2aedaa2"
            ),
            macro_call_interval=6,
            scoped_macros=True,
            expected_macro_edit_misses=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_semantic_project_when_compiling_across_processes_then_cache_is_incremental(
    tmp_path: Path,
    test_case: FreshProcessCompileCachePerformanceGuardTestCase,
) -> None:
    assert_required_cgroup_memory_limit()
    result: FreshProcessCompileCacheBenchmarkResult = run_fresh_process_compile_cache_benchmark(
        project_dir=tmp_path / f"semantic_cache_{test_case.model_count}",
        model_count=test_case.model_count,
        source_count=test_case.source_count,
        seed_count=test_case.seed_count,
        function_count=test_case.function_count,
        macro_count=test_case.macro_count,
        test_count=test_case.test_count,
        audit_count=test_case.audit_count,
        expected_cold_max_wall_seconds=test_case.expected_cold_max_wall_seconds,
        expected_warm_max_wall_seconds=test_case.expected_warm_max_wall_seconds,
        expected_edit_max_wall_seconds=test_case.expected_edit_max_wall_seconds,
        macro_call_interval=test_case.macro_call_interval,
        scoped_macros=test_case.scoped_macros,
    )
    measurements: dict[str, FreshProcessCompileBenchmarkResult] = {
        "cache_disabled": result.cache_disabled,
        "cold": result.cold,
        "warm": result.warm,
        "leaf_edit": result.leaf_edit,
        "after_leaf_edit": result.after_leaf_edit,
        "macro_edit": result.macro_edit,
        "after_macro_edit": result.after_macro_edit,
        "project_config_edit": result.project_config_edit,
        "after_project_config_edit": result.after_project_config_edit,
    }
    for label, measurement in measurements.items():
        _LOGGER.info(
            "fresh-process cache models=%d path=%s wall=%.3fs peak_rss_bytes=%d "
            "fingerprint=%s metrics=%s",
            test_case.model_count,
            label,
            measurement.elapsed_seconds,
            measurement.peak_rss_bytes,
            measurement.semantic_fingerprint,
            fresh_process_compile_cache_metrics(measurement),
        )
    for measurement in measurements.values():
        assert_successful_compile_cache_payload(measurement=measurement, test_case=test_case)
        assert measurement.peak_rss_bytes < test_case.expected_max_rss_bytes

    assert result.cold.elapsed_seconds < test_case.expected_cold_max_wall_seconds
    cache_write_wall_ratio: float = (
        result.cold.elapsed_seconds / result.cache_disabled.elapsed_seconds
    )
    cache_write_cpu_ratio: float = result.cold.cpu_seconds / result.cache_disabled.cpu_seconds
    _LOGGER.info(
        "fresh-process cache models=%d cache-write overhead wall_ratio=%.3f cpu_ratio=%.3f",
        test_case.model_count,
        cache_write_wall_ratio,
        cache_write_cpu_ratio,
    )
    assert cache_write_wall_ratio <= test_case.expected_max_cache_write_wall_overhead_ratio
    assert cache_write_cpu_ratio <= test_case.expected_max_cache_write_cpu_overhead_ratio
    for measurement in (
        result.warm,
        result.after_leaf_edit,
        result.after_macro_edit,
        result.after_project_config_edit,
    ):
        assert measurement.elapsed_seconds < test_case.expected_warm_max_wall_seconds
        assert (
            measurement.elapsed_seconds / result.cold.elapsed_seconds
            <= test_case.expected_max_warm_to_cold_ratio
        )
    for measurement in (result.leaf_edit, result.macro_edit):
        assert measurement.elapsed_seconds < test_case.expected_edit_max_wall_seconds
        assert (
            measurement.elapsed_seconds / result.cold.elapsed_seconds
            <= test_case.expected_max_edit_to_cold_ratio
        )
    assert result.project_config_edit.elapsed_seconds < test_case.expected_cold_max_wall_seconds
    assert result.cache_bytes < test_case.expected_max_cache_bytes

    assert result.cache_disabled.semantic_fingerprint == test_case.expected_cold_fingerprint
    assert result.cold.semantic_fingerprint == test_case.expected_cold_fingerprint
    assert result.warm.semantic_fingerprint == test_case.expected_cold_fingerprint
    assert result.leaf_edit.semantic_fingerprint == test_case.expected_leaf_edit_fingerprint
    assert result.after_leaf_edit.semantic_fingerprint == test_case.expected_leaf_edit_fingerprint
    assert result.macro_edit.semantic_fingerprint == test_case.expected_macro_edit_fingerprint
    assert result.after_macro_edit.semantic_fingerprint == test_case.expected_macro_edit_fingerprint
    assert (
        result.project_config_edit.semantic_fingerprint
        == test_case.expected_project_config_fingerprint
    )
    assert (
        result.after_project_config_edit.semantic_fingerprint
        == test_case.expected_project_config_fingerprint
    )

    assert fresh_process_compile_cache_metrics(result.cache_disabled) == (
        0,
        0,
        0,
        test_case.model_count,
    )
    assert fresh_process_compile_cache_metrics(result.cold) == (0, 0, test_case.model_count, 0)
    assert fresh_process_compile_cache_metrics(result.warm) == (test_case.model_count, 0, 0, 0)
    assert fresh_process_compile_cache_metrics(result.leaf_edit) == (
        test_case.model_count - 1,
        0,
        1,
        0,
    )
    assert_complete_compile_cache_hit(
        measurement=result.after_leaf_edit,
        model_count=test_case.model_count,
    )
    macro_batch_hits, macro_entry_hits, macro_misses, macro_bypasses = (
        fresh_process_compile_cache_metrics(result.macro_edit)
    )
    assert macro_batch_hits + macro_entry_hits + macro_misses == test_case.model_count
    assert macro_batch_hits > 0
    assert macro_misses == test_case.expected_macro_edit_misses
    assert macro_bypasses == 0
    assert_complete_compile_cache_hit(
        measurement=result.after_macro_edit,
        model_count=test_case.model_count,
    )
    config_batch_hits, config_entry_hits, config_misses, config_bypasses = (
        fresh_process_compile_cache_metrics(result.project_config_edit)
    )
    assert config_batch_hits + config_entry_hits + config_misses == test_case.model_count
    assert config_misses > 0
    assert config_bypasses == 0
    assert_complete_compile_cache_hit(
        measurement=result.after_project_config_edit,
        model_count=test_case.model_count,
    )
