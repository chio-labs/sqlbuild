"""Opt-in performance guards for large compile workloads."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompilePerformanceGuardTestCase,
    CompileScalingGuardTestCase,
    DbtShapedCompilePerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    measure_model_sql_bytes,
    run_advanced_compile_benchmark,
    run_dbt_shaped_compile_benchmark,
)


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        CompilePerformanceGuardTestCase(
            description="advanced 3000 model compile stays under eight seconds",
            model_count=3000,
            expected_max_seconds=8.0,
        ),
        CompilePerformanceGuardTestCase(
            description="advanced 10000 model compile stays under twenty-five seconds",
            model_count=10000,
            expected_max_seconds=25.0,
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
    assert large_elapsed_seconds / small_elapsed_seconds < test_case.expected_max_scaling_ratio


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        DbtShapedCompilePerformanceGuardTestCase(
            description="dbt-shaped 3000 model project stays within compile budget",
            model_count=3_000,
            expected_min_sql_bytes=18_000_000,
            expected_max_sql_bytes=25_000_000,
            expected_max_seconds=15.0,
        ),
        DbtShapedCompilePerformanceGuardTestCase(
            description="dbt-shaped 10000 model project stays within compile budget",
            model_count=10_000,
            expected_min_sql_bytes=60_000_000,
            expected_max_sql_bytes=80_000_000,
            expected_max_seconds=45.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_dbt_shaped_project_when_compiling_then_finishes_within_budget(
    tmp_path: Path,
    test_case: DbtShapedCompilePerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"dbt_shaped_{test_case.model_count}"
    elapsed_seconds: float = run_dbt_shaped_compile_benchmark(
        project_dir=project_dir,
        model_count=test_case.model_count,
        expected_max_seconds=test_case.expected_max_seconds,
    )

    total_sql_bytes: int = measure_model_sql_bytes(project_dir)
    assert test_case.expected_min_sql_bytes <= total_sql_bytes
    assert total_sql_bytes <= test_case.expected_max_sql_bytes
    assert elapsed_seconds < test_case.expected_max_seconds
