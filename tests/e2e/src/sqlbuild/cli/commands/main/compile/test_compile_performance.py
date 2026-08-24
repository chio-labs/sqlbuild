"""Opt-in performance guards for large compile workloads."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompileBenchmarkResult,
    CompilePerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    run_advanced_compile_benchmark,
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
    result: CompileBenchmarkResult = run_advanced_compile_benchmark(
        project_dir=tmp_path / f"advanced_{test_case.model_count}",
        model_count=test_case.model_count,
        expected_max_seconds=test_case.expected_max_seconds,
    )

    assert result.elapsed_seconds < test_case.expected_max_seconds


@pytest.mark.performance
def test_given_wide_scan_heavy_projects_when_doubling_sql_size_then_compile_scales_linearly(
    tmp_path: Path,
) -> None:
    model_count: int = 16
    expected_max_seconds: float = 8.0
    small_result: CompileBenchmarkResult = run_advanced_compile_benchmark(
        project_dir=tmp_path / "wide_small",
        model_count=model_count,
        scan_event_lines_per_model=2000,
        expected_max_seconds=expected_max_seconds,
    )
    large_result: CompileBenchmarkResult = run_advanced_compile_benchmark(
        project_dir=tmp_path / "wide_large",
        model_count=model_count,
        scan_event_lines_per_model=4000,
        expected_max_seconds=expected_max_seconds,
    )

    assert small_result.total_sql_bytes >= 2_000_000
    assert large_result.total_sql_bytes >= 4_000_000
    assert small_result.generated_scan_events == 32_000
    assert large_result.generated_scan_events == 64_000
    assert large_result.elapsed_seconds / small_result.elapsed_seconds < 3.0
