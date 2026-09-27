"""End-to-end tests for the same-runner compile performance ratio guard."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.scripts.compile_performance_ratio._test_types import (
    CompilePerformanceRatioTestCase,
)

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize(
    "test_case",
    (
        CompilePerformanceRatioTestCase(
            description="identical builds pass a generous limit",
            kind="dense",
            models=20,
            max_ratio="3.0",
            expected_return_code=0,
            expected_fragments=("| Wall (s) |", "| CPU (s) |", "| analysis_native_ms |"),
        ),
        CompilePerformanceRatioTestCase(
            description="an unattainable limit fails with the exceeded ratios",
            kind="dense",
            models=20,
            max_ratio="0.01",
            expected_return_code=1,
            expected_fragments=("Compile performance regression: wall ratio",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_two_builds_when_comparing_compile_performance_then_enforces_ratio_limit(
    test_case: CompilePerformanceRatioTestCase,
) -> None:
    environment: dict[str, str] = dict(os.environ)
    _ = environment.pop("GITHUB_STEP_SUMMARY", None)
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.compare_compile_performance",
            "--kind",
            test_case.kind,
            "--models",
            str(test_case.models),
            "--runs",
            "1",
            "--base-python",
            sys.executable,
            "--head-python",
            sys.executable,
            "--max-ratio",
            test_case.max_ratio,
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_return_code, output
    for fragment in test_case.expected_fragments:
        assert fragment in output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
