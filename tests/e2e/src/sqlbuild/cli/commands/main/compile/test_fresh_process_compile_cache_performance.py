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
_MAX_WARM_TO_COLD_RATIO: float = 0.67


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
            expected_cold_max_wall_seconds=14.0,
            expected_warm_max_wall_seconds=8.0,
            expected_edit_max_wall_seconds=7.5,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=96 * _MIB,
            expected_cold_fingerprint=(
                "36e2274af2bd6840f41d88ee1140a91034505a50f7fa27b61e2e47aa06765314"
            ),
            expected_leaf_edit_fingerprint=(
                "f6cfcbb21bf7e011b76f08f5d8e61b2095316b6845d987090e79b1718ed54175"
            ),
            expected_macro_edit_fingerprint=(
                "ae102976a43c0fd6a68e5e55a7feeb9fac5f49ffc56bd3cdfcd389e199582081"
            ),
            expected_project_config_fingerprint=(
                "96e996a556119f452e966096747b35219941bf7bd324624242aadf6375ba1a31"
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
            expected_cold_max_wall_seconds=23.0,
            expected_warm_max_wall_seconds=14.0,
            expected_edit_max_wall_seconds=13.5,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=160 * _MIB,
            expected_cold_fingerprint=(
                "686664bcadbbb0e339205d71b8fb3ab2d3f1226ca888eb4b2e6a5aa97ade1efb"
            ),
            expected_leaf_edit_fingerprint=(
                "43fa1db2d5db12c5031aef8f6fb2a0e4af89c51ece58b1f1772db0a9ea4d43a0"
            ),
            expected_macro_edit_fingerprint=(
                "fd0cc80586b11d8d79a904d1daa6da4d559d22d6b4ebea02139a7d12626b770f"
            ),
            expected_project_config_fingerprint=(
                "44a292e9ada77cc7038036fb593d9d8d8cd4883062a07254d963963ed0b4bb45"
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
            expected_cold_max_wall_seconds=46.5,
            expected_warm_max_wall_seconds=27.0,
            expected_edit_max_wall_seconds=24.5,
            expected_max_warm_to_cold_ratio=_MAX_WARM_TO_COLD_RATIO,
            expected_max_rss_bytes=2 * _GIB,
            expected_max_cache_bytes=320 * _MIB,
            expected_cold_fingerprint=(
                "c1364cae404ee768c4443c3b964c42370e33268fbf83b101890b13558290e3e0"
            ),
            expected_leaf_edit_fingerprint=(
                "fe35feb1b239a17ed0e7b22bca20c2af06e0f25335fe5f9fae212491a693911b"
            ),
            expected_macro_edit_fingerprint=(
                "bec17e83316ca926b76f450fa8a035e83f19c061e14a11b8effe04b7fa2e26fd"
            ),
            expected_project_config_fingerprint=(
                "780e26aa973459fbc803dd8d64315d445aab8bc57e90b0ad1ecb94f074b22474"
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
