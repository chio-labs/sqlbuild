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
                "c7c4d0e6449728dd6ee59538a1a482d454418f54e617f2ffb4e24fb969dabac9"
            ),
            expected_leaf_edit_fingerprint=(
                "1a5ca199da90a44604e3f855c4ca703374315732f3b4e21084de3550f2d46de7"
            ),
            expected_macro_edit_fingerprint=(
                "fa0368493144fd99939f3a8ea8449e0c33bf05095cdf4a18975f77243a7c749e"
            ),
            expected_project_config_fingerprint=(
                "d3bf664c6dcb737522fd8e42fc950e91f085a684292eaf028a65cccd4fca62ed"
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
                "efb34659a1f5ac37221c36ee0f21e880f95fb668339f9ea61faddc6922607b30"
            ),
            expected_leaf_edit_fingerprint=(
                "7d8d0283e958bd00faf77e675e84185a78ff7a366393610b67ba43f77106d823"
            ),
            expected_macro_edit_fingerprint=(
                "b8218285d114afa179c63e6da5cf519743d89a21481f52068fc5044f5f3bec36"
            ),
            expected_project_config_fingerprint=(
                "658c9cbcd8cbdaddc7dd6f06211ae830074c686101c8814afcc0f9ed53c0defd"
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
                "766d9e58c926a0aabda70280a36e816b6efe120c1948aef85375f3d2ecdfb078"
            ),
            expected_leaf_edit_fingerprint=(
                "6d0591c75b51daf3de94a873f5faa63f262a09d09f4d59c02fe1ba8c05e5ac14"
            ),
            expected_macro_edit_fingerprint=(
                "1b3bd8a3040eb092312ab520f4a842a1bb930b741d7b8ddfa06b472d72eaff54"
            ),
            expected_project_config_fingerprint=(
                "e5a20011e3c48d82301c8d65238d532ae4479638e10cd5cb3477ad9293074dd1"
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
