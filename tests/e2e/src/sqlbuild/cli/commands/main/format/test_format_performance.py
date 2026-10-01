"""Opt-in performance guard for large contract-aware format workloads."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from scripts.format_performance._helpers.model_project import write_model_format_project
from tests.e2e.src.sqlbuild.cli.commands.main.format._test_types import (
    FormatPerformanceGuardTestCase,
    FormatScalingGuardTestCase,
    ModelFormatPerformanceTestCase,
    ModelFormatScalingTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.format.helpers import (
    count_typed_null_candidates,
    run_format_check,
    write_format_performance_project,
)

_FORMAT_ELAPSED_PATTERN: re.Pattern[str] = re.compile(r"Formatting SQL  OK  \(([0-9.]+)s;")


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        FormatPerformanceGuardTestCase(
            description="one thousand contract fixtures format within bounded work and time",
            model_count=250,
            test_count=1_000,
            expected_test_file_count=1_000,
            expected_typed_null_candidate_count=1_000,
            expected_max_elapsed_seconds=12.0,
            expected_max_format_seconds=5.0,
            hard_ceiling_seconds=20.0,
            expected_returncode=1,
        ),
        FormatPerformanceGuardTestCase(
            description="one thousand fixture-only rewrites complete without canonical churn",
            model_count=250,
            test_count=1_000,
            expected_test_file_count=1_000,
            expected_typed_null_candidate_count=1_000,
            expected_max_elapsed_seconds=6.0,
            expected_max_format_seconds=2.0,
            hard_ceiling_seconds=12.0,
            expected_returncode=1,
            additional_arguments=("--fixtures-only",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_contract_heavy_project_when_formatting_tests_then_work_and_time_stay_bounded(
    tmp_path: Path,
    test_case: FormatPerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / "format_performance"
    write_format_performance_project(
        project_dir=project_dir,
        model_count=test_case.model_count,
        test_count=test_case.test_count,
    )
    test_files: tuple[Path, ...] = tuple((project_dir / "tests").rglob("*.sql"))
    candidate_count: int = count_typed_null_candidates(project_dir=project_dir)

    started_at: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "format",
            "--check",
            *test_case.additional_arguments,
            "--select",
            "path:tests",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=test_case.hard_ceiling_seconds,
    )
    elapsed_seconds: float = time.perf_counter() - started_at
    elapsed_match: re.Match[str] | None = _FORMAT_ELAPSED_PATTERN.search(result.stderr)

    assert result.returncode == test_case.expected_returncode
    assert len(test_files) == test_case.expected_test_file_count
    assert candidate_count == test_case.expected_typed_null_candidate_count
    assert count_typed_null_candidates(project_dir=project_dir) == candidate_count
    assert f"{test_case.expected_test_file_count} files checked" in result.stderr
    assert f"{test_case.expected_test_file_count} changed" in result.stderr
    assert elapsed_match is not None
    assert float(elapsed_match.group(1)) <= test_case.expected_max_format_seconds
    assert elapsed_seconds <= test_case.expected_max_elapsed_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        FormatScalingGuardTestCase(
            description="contract fixture formatting scales linearly across doublings",
            test_counts=(500, 1_000, 2_000),
            model_count=250,
            expected_max_doubling_ratio=2.75,
            expected_max_largest_elapsed_seconds=12.0,
            hard_ceiling_seconds=20.0,
            expected_returncode=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_doubling_fixture_counts_when_formatting_then_elapsed_time_scales_linearly(
    tmp_path: Path,
    test_case: FormatScalingGuardTestCase,
) -> None:
    elapsed_samples: list[float] = []
    format_samples: list[float] = []
    for test_count in test_case.test_counts:
        project_dir: Path = tmp_path / f"format_scaling_{test_count}"
        write_format_performance_project(
            project_dir=project_dir,
            model_count=test_case.model_count,
            test_count=test_count,
        )

        started_at: float = time.perf_counter()
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [
                str(Path(sys.executable).with_name("sqb")),
                "--project-dir",
                str(project_dir),
                "--no-color",
                "format",
                "--check",
                "--select",
                "path:tests",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=test_case.hard_ceiling_seconds,
        )
        elapsed_seconds: float = time.perf_counter() - started_at
        elapsed_match: re.Match[str] | None = _FORMAT_ELAPSED_PATTERN.search(result.stderr)

        assert result.returncode == test_case.expected_returncode
        assert count_typed_null_candidates(project_dir=project_dir) == test_count
        assert f"{test_count} files checked" in result.stderr
        assert elapsed_match is not None
        elapsed_samples.append(elapsed_seconds)
        format_samples.append(float(elapsed_match.group(1)))

    assert elapsed_samples[-1] <= test_case.expected_max_largest_elapsed_seconds
    for samples in (elapsed_samples, format_samples):
        for smaller, larger in zip(samples[:-1], samples[1:], strict=True):
            assert larger / smaller <= test_case.expected_max_doubling_ratio


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        ModelFormatPerformanceTestCase(
            description="1,300 unformatted models of mixed shape format within budget",
            model_count=1_300,
            large_model_lines=0,
            expected_file_count=1_300,
            expected_max_format_seconds=1.5,
            expected_max_elapsed_seconds=3.5,
            hard_ceiling_seconds=30.0,
        ),
        ModelFormatPerformanceTestCase(
            description="one 6,000-line model with 3,000 CTEs formats within budget",
            model_count=0,
            large_model_lines=6_000,
            expected_file_count=1,
            expected_max_format_seconds=0.75,
            expected_max_elapsed_seconds=2.5,
            hard_ceiling_seconds=30.0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unformatted_models_when_checking_format_then_time_stays_bounded(
    tmp_path: Path,
    test_case: ModelFormatPerformanceTestCase,
) -> None:
    project_dir: Path = tmp_path / "model_format_performance"
    write_model_format_project(
        project_dir=project_dir,
        model_count=test_case.model_count,
        large_model_lines=test_case.large_model_lines,
    )

    result, elapsed_seconds, format_seconds = run_format_check(
        project_dir=project_dir, timeout_seconds=test_case.hard_ceiling_seconds
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    assert "format-unsafe" not in result.stdout + result.stderr
    assert (
        f"{test_case.expected_file_count} files checked, {test_case.expected_file_count} changed"
        in result.stderr
    )
    assert format_seconds <= test_case.expected_max_format_seconds
    assert elapsed_seconds <= test_case.expected_max_elapsed_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        ModelFormatScalingTestCase(
            description="unformatted model formatting scales linearly across doublings",
            model_counts=(325, 650, 1_300),
            expected_max_doubling_ratio=2.75,
            hard_ceiling_seconds=30.0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_doubling_model_counts_when_checking_format_then_format_time_scales_linearly(
    tmp_path: Path,
    test_case: ModelFormatScalingTestCase,
) -> None:
    format_samples: list[float] = []
    for model_count in test_case.model_counts:
        project_dir: Path = tmp_path / f"model_format_scaling_{model_count}"
        write_model_format_project(project_dir=project_dir, model_count=model_count)
        result, _, format_seconds = run_format_check(
            project_dir=project_dir, timeout_seconds=test_case.hard_ceiling_seconds
        )
        assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
        format_samples.append(format_seconds)

    for smaller, larger in zip(format_samples[:-1], format_samples[1:], strict=True):
        assert larger <= smaller * test_case.expected_max_doubling_ratio + 0.05
