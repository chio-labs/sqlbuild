"""End-to-end tests for the same-runner compile performance ratio guard."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.e2e.scripts.compile_performance_ratio._test_types import (
    CompilePerformanceRatioTestCase,
    PerSideCompilePerformanceRatioTestCase,
)
from tests.e2e.scripts.compile_performance_ratio.helpers import (
    FAILING_GENERATOR,
    MARKER_GENERATOR,
    logged_projects,
    write_fake_base_root,
    write_logging_python,
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


@pytest.mark.parametrize(
    "test_case",
    (
        PerSideCompilePerformanceRatioTestCase(
            description="each build compiles the project its own generator wrote",
            base_generator=MARKER_GENERATOR,
            expected_return_code=0,
            expected_fragments=("Projects generated per side",),
            expected_base_projects=("base", "base"),
            expected_head_projects=("head", "head"),
        ),
        PerSideCompilePerformanceRatioTestCase(
            description="a failing base generator stops before any compile",
            base_generator=FAILING_GENERATOR,
            expected_return_code=1,
            expected_fragments=("base project generation in", "base generator exploded"),
            expected_base_projects=(),
            expected_head_projects=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_base_root_when_comparing_compile_performance_then_each_side_uses_its_project(
    test_case: PerSideCompilePerformanceRatioTestCase, tmp_path: Path
) -> None:
    base_root: Path = write_fake_base_root(
        root=tmp_path / "base", generator=test_case.base_generator
    )
    base_log: Path = tmp_path / "base.log"
    head_log: Path = tmp_path / "head.log"
    base_python: Path = write_logging_python(path=tmp_path / "base-python", log=base_log)
    head_python: Path = write_logging_python(path=tmp_path / "head-python", log=head_log)
    environment: dict[str, str] = dict(os.environ)
    _ = environment.pop("GITHUB_STEP_SUMMARY", None)

    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.compare_compile_performance",
            "--kind",
            "dense",
            "--models",
            "20",
            "--runs",
            "1",
            "--base-root",
            str(base_root),
            "--base-python",
            str(base_python),
            "--head-python",
            str(head_python),
            "--max-ratio",
            "1000",
        ],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_return_code, output
    assert all(fragment in output for fragment in test_case.expected_fragments), output
    assert logged_projects(base_log) == test_case.expected_base_projects
    assert logged_projects(head_log) == test_case.expected_head_projects


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
