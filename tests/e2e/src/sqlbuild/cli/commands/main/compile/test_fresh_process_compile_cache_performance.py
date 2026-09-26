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
_MAX_WARM_TO_COLD_RATIO: float = 0.65
_MAX_EDIT_TO_COLD_RATIO: float = 0.60


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
            expected_cold_max_wall_seconds=14.5,
            expected_warm_max_wall_seconds=8.25,
            expected_edit_max_wall_seconds=7.25,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_edit_to_cold_ratio=_MAX_EDIT_TO_COLD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=96 * _MIB,
            expected_cold_fingerprint=(
                "8954a992c0edd153e59edcab1f7f5056e273d94844960de91c6d177e516d9703"
            ),
            expected_leaf_edit_fingerprint=(
                "5bab0980330c64c09f4243726da346e2395ba56b5be88966267f2fb291bda5bf"
            ),
            expected_macro_edit_fingerprint=(
                "7c26cbe075e6144e1cac4d1149a6f34c16d9d05c3dc01ec373098080ee7a676a"
            ),
            expected_project_config_fingerprint=(
                "9a3868b5d90d1260bec67267b1ed3aff81f49191318d6d67466cca5792e3ddde"
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
            expected_cold_max_wall_seconds=23.5,
            expected_warm_max_wall_seconds=13.5,
            expected_edit_max_wall_seconds=12.0,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_edit_to_cold_ratio=_MAX_EDIT_TO_COLD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=160 * _MIB,
            expected_cold_fingerprint=(
                "08cf0b5e5a87ee6a0fce8018d8b73c05fd6814c227478c55b35ced9d33b68aac"
            ),
            expected_leaf_edit_fingerprint=(
                "8a22e736a25eb7edc8e87d800e14cb5d3c9765f5316cfe58bfa59bf37306fa63"
            ),
            expected_macro_edit_fingerprint=(
                "7edc285356a565d2ced71de99494f79a56859ab08e54cbc6f61271f75e214c6b"
            ),
            expected_project_config_fingerprint=(
                "f39a5b140c8b6987d3da96117b3e24cb731fd1e863d4283585564c9aa8bb5c41"
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
            expected_cold_max_wall_seconds=42.5,
            expected_warm_max_wall_seconds=24.5,
            expected_edit_max_wall_seconds=22.0,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_edit_to_cold_ratio=_MAX_EDIT_TO_COLD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=320 * _MIB,
            expected_cold_fingerprint=(
                "40f1366e177909ec4e42544e929adaaa91bab4ee3a3d57bdce61e09ee42bab9b"
            ),
            expected_leaf_edit_fingerprint=(
                "86c6883c8f7d40e027edbd8bd980319c49b60137c0131a779c7b2dff0efecf4b"
            ),
            expected_macro_edit_fingerprint=(
                "de09b2dd620dfdf9e61293620928049bae744772baa2410ec009d6bd456dd86d"
            ),
            expected_project_config_fingerprint=(
                "87be1c4f9a0893b35ba9b2fe8c16065e3491089ffd58c2aada6a2551284f15fd"
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

    assert fresh_process_compile_cache_metrics(result.cold) == (0, 0, test_case.model_count, 0)
    assert fresh_process_compile_cache_metrics(result.warm) == (test_case.model_count, 0, 0, 0)
    assert fresh_process_compile_cache_metrics(result.leaf_edit) == (
        test_case.model_count - 1,
        0,
        1,
        0,
    )
    assert fresh_process_compile_cache_metrics(result.after_leaf_edit) == (
        test_case.model_count - 1,
        1,
        0,
        0,
    )
    macro_batch_hits, macro_entry_hits, macro_misses, macro_bypasses = (
        fresh_process_compile_cache_metrics(result.macro_edit)
    )
    assert macro_batch_hits + macro_entry_hits + macro_misses == test_case.model_count
    assert macro_batch_hits > 0
    assert macro_entry_hits > 0
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
