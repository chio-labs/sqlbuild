"""Fresh-process warm and edit budgets for structurally diverse all-rules SQL."""

import logging
from pathlib import Path
from typing import cast

import pytest

from scripts.cold_compile_performance._helpers.varied_benchmark import (
    run_varied_cache_benchmark,
)
from scripts.cold_compile_performance._helpers.varied_statistics import varied_project_statistics
from scripts.cold_compile_performance.main.assert_required_cgroup_memory_limit import (
    assert_required_cgroup_memory_limit,
)
from scripts.cold_compile_performance.models import VariedProjectStatistics
from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import VariedCompileCacheTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    FreshProcessCompileBenchmarkResult,
    fresh_process_compile_cache_metrics,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


@pytest.mark.performance
@pytest.mark.cache_compile_performance
@pytest.mark.parametrize(
    "test_case",
    (
        VariedCompileCacheTestCase(
            "models_1000_varied_shared_graph",
            1000,
            24.0,
            10.0,
            13.0,
            2 * 1024**3,
            950,
            900,
            40,
            60,
            150,
            400,
            150,
            250,
            (
                "5f19b80bf5489a45b2e41d855dd2cd8bde666b6a7501c62075395d8d6672349f",
                "b5382d648c3ba1958eb92f389c4850553792b291e3c7247e32d9d6eb349bda78",
                "52021ad38f0a073ac26b7d05b95286e34410ec1de46307304ef085e3ed00a0a0",
                "a31410ae730692393c913275ae00b47ef797896c9d0e2f1ac1bb6afd3a532678",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_varied_shared_graph_when_compiling_warm_and_edits_then_budgets_and_oracles_hold(
    test_case: VariedCompileCacheTestCase,
    tmp_path: Path,
) -> None:
    assert_required_cgroup_memory_limit()
    measurements: dict[str, FreshProcessCompileBenchmarkResult] = run_varied_cache_benchmark(
        project_dir=tmp_path / "varied_orders",
        test_case=test_case,
    )
    statistics: VariedProjectStatistics = varied_project_statistics(measurements["cold"].payload)
    _LOGGER.info("varied project structure: %s", statistics)
    assert statistics.model_count == test_case.model_count
    assert statistics.distinct_operator_shapes >= test_case.expected_min_operator_shapes
    assert statistics.largest_component >= test_case.expected_min_component
    assert test_case.expected_min_depth <= statistics.maximum_depth <= test_case.expected_max_depth
    assert test_case.expected_min_leaves <= statistics.leaf_models <= test_case.expected_max_leaves
    assert statistics.array_models >= test_case.expected_min_array_models
    assert statistics.window_models >= test_case.expected_min_window_models
    for label, result in measurements.items():
        _LOGGER.info(
            "varied cache path=%s wall=%.3fs peak_rss_bytes=%d fingerprint=%s metrics=%s",
            label,
            result.elapsed_seconds,
            result.peak_rss_bytes,
            result.semantic_fingerprint,
            fresh_process_compile_cache_metrics(result),
        )
        assert result.payload["diagnostics"] == []
        assert result.payload["has_errors"] is False
        assert result.peak_rss_bytes < test_case.expected_max_rss_bytes
    assert measurements["cold"].semantic_fingerprint == measurements["warm"].semantic_fingerprint
    assert measurements["cold"].elapsed_seconds < test_case.expected_cold_max_seconds
    assert fresh_process_compile_cache_metrics(measurements["cold"]) == (
        0,
        0,
        test_case.model_count,
        0,
    )
    cold_timings: dict[str, int] = cast(
        dict[str, int], measurements["cold"].payload["compile_timings"]
    )
    assert cold_timings["rule_cache_hits"] == 0
    assert (
        tuple(
            measurements[label].semantic_fingerprint
            for label in ("cold", "leaf", "shared", "macro")
        )
        == test_case.expected_fingerprints
    )
    for label in ("warm", "after_leaf", "after_shared", "after_macro"):
        assert measurements[label].elapsed_seconds < test_case.expected_warm_max_seconds
        batch_hits, entry_hits, misses, bypasses = fresh_process_compile_cache_metrics(
            measurements[label]
        )
        assert batch_hits + entry_hits == test_case.model_count
        assert misses == bypasses == 0
        timings: dict[str, int] = cast(
            dict[str, int], measurements[label].payload["compile_timings"]
        )
        assert timings["rule_cache_misses"] == 0
        assert timings["rule_cache_hits"] > 0
    for label in ("leaf", "shared", "macro"):
        result: FreshProcessCompileBenchmarkResult = measurements[label]
        assert result.elapsed_seconds < test_case.expected_edit_max_seconds
        assert result.semantic_fingerprint == measurements[f"after_{label}"].semantic_fingerprint
        assert result.semantic_fingerprint == measurements[f"oracle_{label}"].semantic_fingerprint
        batch_hits, entry_hits, misses, bypasses = fresh_process_compile_cache_metrics(result)
        assert 0 < misses < test_case.model_count
        assert batch_hits + entry_hits + misses == test_case.model_count
        assert bypasses == 0
        assert fresh_process_compile_cache_metrics(measurements[f"oracle_{label}"]) == (
            0,
            0,
            0,
            test_case.model_count,
        )
        oracle_timings: dict[str, int] = cast(
            dict[str, int], measurements[f"oracle_{label}"].payload["compile_timings"]
        )
        assert oracle_timings["rule_cache_hits"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
