"""Opt-in performance guards for large compile workloads."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompilePerformanceGuardTestCase,
    CompileScalingGuardTestCase,
    DbtShapedCompilePerformanceGuardTestCase,
    SqlTestHeavyCompilePerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    measure_compiled_test_sql_bytes,
    measure_model_sql_bytes,
    run_advanced_compile_benchmark,
    run_dbt_shaped_compile_benchmark,
    run_test_heavy_compile_benchmark,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        CompilePerformanceGuardTestCase(
            description="advanced 3000 model compile stays under three seconds",
            model_count=3000,
            expected_max_seconds=3.0,
        ),
        CompilePerformanceGuardTestCase(
            description="advanced 10000 model compile stays under nine seconds",
            model_count=10000,
            expected_max_seconds=9.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_generated_advanced_project_when_compiling_then_finishes_within_budget(
    tmp_path: Path,
    test_case: CompilePerformanceGuardTestCase,
) -> None:
    elapsed_seconds: float = run_advanced_compile_benchmark(
        project_dir=tmp_path / f"advanced_{test_case.model_count}",
        model_count=test_case.model_count,
        expected_max_seconds=test_case.expected_max_seconds,
    )
    _LOGGER.info(
        f"advanced compile models={test_case.model_count} "
        f"cold={elapsed_seconds:.3f}s budget={test_case.expected_max_seconds:g}s"
    )

    assert elapsed_seconds < test_case.expected_max_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        CompileScalingGuardTestCase(
            description="doubling wide SQL scan events remains sub-quadratic",
            model_count=16,
            small_scan_event_lines_per_model=2000,
            large_scan_event_lines_per_model=4000,
            expected_min_small_sql_bytes=2_000_000,
            expected_min_large_sql_bytes=4_000_000,
            expected_small_scan_events=32_000,
            expected_large_scan_events=64_000,
            expected_max_seconds=8.0,
            expected_max_scaling_ratio=3.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_wide_scan_heavy_projects_when_doubling_sql_size_then_compile_scales_linearly(
    tmp_path: Path,
    test_case: CompileScalingGuardTestCase,
) -> None:
    small_project_dir: Path = tmp_path / "wide_small"
    large_project_dir: Path = tmp_path / "wide_large"
    small_elapsed_seconds: float = run_advanced_compile_benchmark(
        project_dir=small_project_dir,
        model_count=test_case.model_count,
        scan_event_lines_per_model=test_case.small_scan_event_lines_per_model,
        expected_max_seconds=test_case.expected_max_seconds,
    )
    large_elapsed_seconds: float = run_advanced_compile_benchmark(
        project_dir=large_project_dir,
        model_count=test_case.model_count,
        scan_event_lines_per_model=test_case.large_scan_event_lines_per_model,
        expected_max_seconds=test_case.expected_max_seconds,
    )
    scaling_ratio: float = large_elapsed_seconds / small_elapsed_seconds
    _LOGGER.info(
        f"wide compile small={small_elapsed_seconds:.3f}s large={large_elapsed_seconds:.3f}s "
        f"ratio={scaling_ratio:.3f} budget={test_case.expected_max_scaling_ratio:.1f}"
    )

    assert measure_model_sql_bytes(small_project_dir) >= test_case.expected_min_small_sql_bytes
    assert measure_model_sql_bytes(large_project_dir) >= test_case.expected_min_large_sql_bytes
    assert (
        test_case.model_count * test_case.small_scan_event_lines_per_model
        == test_case.expected_small_scan_events
    )
    assert (
        test_case.model_count * test_case.large_scan_event_lines_per_model
        == test_case.expected_large_scan_events
    )
    assert scaling_ratio < test_case.expected_max_scaling_ratio


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        DbtShapedCompilePerformanceGuardTestCase(
            description="dbt-shaped 3000 model cold and warm compiles stay within budget",
            model_count=3_000,
            expected_min_sql_bytes=18_000_000,
            expected_max_sql_bytes=25_000_000,
            expected_max_seconds=4.0,
            expected_warm_max_seconds=2.25,
        ),
        DbtShapedCompilePerformanceGuardTestCase(
            description="dbt-shaped 10000 model cold and warm compiles stay within budget",
            model_count=10_000,
            expected_min_sql_bytes=60_000_000,
            expected_max_sql_bytes=80_000_000,
            expected_max_seconds=13.0,
            expected_warm_max_seconds=8.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_shaped_project_when_compiling_cold_and_warm_then_finishes_within_budgets(
    tmp_path: Path,
    test_case: DbtShapedCompilePerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"dbt_shaped_{test_case.model_count}"
    cold_seconds, warm_seconds = run_dbt_shaped_compile_benchmark(
        project_dir=project_dir,
        model_count=test_case.model_count,
        expected_max_seconds=test_case.expected_max_seconds,
        expected_warm_max_seconds=test_case.expected_warm_max_seconds,
    )
    _LOGGER.info(
        f"dbt-shaped compile models={test_case.model_count} cold={cold_seconds:.3f}s "
        f"warm={warm_seconds:.3f}s budgets={test_case.expected_max_seconds:g}s/"
        f"{test_case.expected_warm_max_seconds:g}s"
    )

    total_sql_bytes: int = measure_model_sql_bytes(project_dir)
    assert test_case.expected_min_sql_bytes <= total_sql_bytes
    assert total_sql_bytes <= test_case.expected_max_sql_bytes
    assert cold_seconds < test_case.expected_max_seconds
    assert warm_seconds < test_case.expected_warm_max_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestHeavyCompilePerformanceGuardTestCase(
            description="1000 models and 150 chained native tests compile under seven seconds",
            model_count=1_000,
            test_count=150,
            chain_depth=5,
            fixture_row_count=120,
            expected_min_compiled_test_bytes=2_000_000,
            expected_max_seconds=7.0,
            expected_warm_max_seconds=3.0,
            expected_edit_max_seconds=4.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_test_heavy_project_when_compiling_then_finishes_within_budget(
    tmp_path: Path,
    test_case: SqlTestHeavyCompilePerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / "test_heavy"
    cold_seconds, warm_seconds, model_edit_seconds, test_edit_seconds = (
        run_test_heavy_compile_benchmark(
            project_dir=project_dir,
            model_count=test_case.model_count,
            test_count=test_case.test_count,
            chain_depth=test_case.chain_depth,
            fixture_row_count=test_case.fixture_row_count,
            expected_max_seconds=test_case.expected_max_seconds,
            expected_warm_max_seconds=test_case.expected_warm_max_seconds,
            expected_edit_max_seconds=test_case.expected_edit_max_seconds,
        )
    )
    compiled_test_bytes: int = measure_compiled_test_sql_bytes(project_dir)
    _LOGGER.info(
        f"test-heavy compile models={test_case.model_count} tests={test_case.test_count} "
        f"compiled_test_bytes={compiled_test_bytes} cold={cold_seconds:.3f}s "
        f"warm={warm_seconds:.3f}s model_edit={model_edit_seconds:.3f}s "
        f"test_edit={test_edit_seconds:.3f}s budgets={test_case.expected_max_seconds:g}s/"
        f"{test_case.expected_warm_max_seconds:g}s/{test_case.expected_edit_max_seconds:g}s"
    )

    assert compiled_test_bytes >= test_case.expected_min_compiled_test_bytes
    assert cold_seconds < test_case.expected_max_seconds
    assert warm_seconds < test_case.expected_warm_max_seconds
    assert model_edit_seconds < test_case.expected_edit_max_seconds
    assert test_edit_seconds < test_case.expected_edit_max_seconds
