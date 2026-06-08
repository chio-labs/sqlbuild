"""Opt-in performance guards for large compile workloads."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.compile._test_types import (
    CompilePerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.compile.helpers import (
    run_advanced_compile_benchmark,
)

TEST_CASES: list[CompilePerformanceGuardTestCase] = [
    CompilePerformanceGuardTestCase(
        description="advanced 3000 model compile stays under eight seconds",
        model_count=3000,
        expected_max_seconds=8.0,
    ),
    CompilePerformanceGuardTestCase(
        description="advanced 10000 model compile stays under twenty seconds",
        model_count=10000,
        expected_max_seconds=20.0,
    ),
]


@pytest.mark.performance
@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
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
