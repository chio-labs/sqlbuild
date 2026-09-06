"""Opt-in performance guards for large native lint workloads."""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.e2e.src.sqlbuild.cli.commands.main.lint._test_types import (
    FixPerformanceGuardTestCase,
    LintPerformanceBehaviorTestCase,
    LintPerformanceGuardTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.lint.helpers import (
    CLEAN_MODEL_SQL,
    CONFLICTING_FIX_MODEL_SQL,
    DIRTY_MODEL_SQL,
    SKIPPED_FIX_MODEL_SQL,
    write_lint_performance_project,
    write_pathological_lint_project,
    write_varied_production_lint_project,
)

_LOGGER: logging.Logger = logging.getLogger(__name__)


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        LintPerformanceGuardTestCase(
            description="clean 3000 model native lint stays under four seconds",
            model_count=3_000,
            hard_ceiling_seconds=8,
            expected_max_elapsed_seconds=4.0,
            model_sql=CLEAN_MODEL_SQL,
        ),
        LintPerformanceGuardTestCase(
            description="clean 10000 model native lint stays under twelve seconds",
            model_count=10_000,
            hard_ceiling_seconds=20,
            expected_max_elapsed_seconds=12.0,
            model_sql=CLEAN_MODEL_SQL,
        ),
        LintPerformanceGuardTestCase(
            description="dirty 3000 model native lint stays under eight seconds",
            model_count=3_000,
            hard_ceiling_seconds=14,
            expected_max_elapsed_seconds=8.0,
            model_sql=DIRTY_MODEL_SQL,
            expected_exit_code=1,
        ),
        LintPerformanceGuardTestCase(
            description="dirty 10000 model native lint stays under twenty five seconds",
            model_count=10_000,
            hard_ceiling_seconds=35,
            expected_max_elapsed_seconds=25.0,
            model_sql=DIRTY_MODEL_SQL,
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_project_when_native_linting_then_finishes_within_budget(
    tmp_path: Path,
    test_case: LintPerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"lint_{test_case.model_count}"
    write_lint_performance_project(
        project_dir=project_dir,
        model_count=test_case.model_count,
        model_sql=test_case.model_sql,
    )

    started_at: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "lint",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=test_case.hard_ceiling_seconds,
    )
    elapsed_seconds: float = time.perf_counter() - started_at
    _LOGGER.info(
        f"native lint models={test_case.model_count} elapsed={elapsed_seconds:.3f}s "
        f"budget={test_case.expected_max_elapsed_seconds:g}s"
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert elapsed_seconds < test_case.expected_max_elapsed_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        LintPerformanceGuardTestCase(
            description="varied production-shaped 3000 model lint stays under eight seconds",
            model_count=3_000,
            hard_ceiling_seconds=12,
            expected_max_elapsed_seconds=8.0,
            model_sql="",
        ),
        LintPerformanceGuardTestCase(
            description="varied production-shaped 10000 model lint stays under fifteen seconds",
            model_count=10_000,
            hard_ceiling_seconds=20,
            expected_max_elapsed_seconds=15.0,
            model_sql="",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_varied_production_project_when_linting_then_scales_without_cache_shortcut(
    tmp_path: Path,
    test_case: LintPerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"varied_lint_{test_case.model_count}"
    write_varied_production_lint_project(
        project_dir=project_dir,
        model_count=test_case.model_count,
    )

    started_at: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "lint",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=test_case.hard_ceiling_seconds,
    )
    elapsed_seconds: float = time.perf_counter() - started_at
    _LOGGER.info(
        f"varied production lint models={test_case.model_count} "
        f"elapsed={elapsed_seconds:.3f}s budget={test_case.expected_max_elapsed_seconds:g}s"
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed_seconds < test_case.expected_max_elapsed_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        FixPerformanceGuardTestCase(
            description="clean 3000 model fix check stays under eight seconds",
            model_count=3_000,
            hard_ceiling_seconds=14,
            expected_max_elapsed_seconds=8.0,
            model_sql=CLEAN_MODEL_SQL,
            expected_exit_code=0,
        ),
        FixPerformanceGuardTestCase(
            description="fixable 3000 model fix check stays under fifteen seconds",
            model_count=3_000,
            hard_ceiling_seconds=22,
            expected_max_elapsed_seconds=15.0,
            model_sql=DIRTY_MODEL_SQL,
            expected_exit_code=1,
        ),
        FixPerformanceGuardTestCase(
            description="skipped 3000 model fix check stays under fifteen seconds",
            model_count=3_000,
            hard_ceiling_seconds=22,
            expected_max_elapsed_seconds=15.0,
            model_sql=SKIPPED_FIX_MODEL_SQL,
            expected_exit_code=1,
        ),
        FixPerformanceGuardTestCase(
            description="overlapping 3000 model fix check stays under twenty seconds",
            model_count=3_000,
            hard_ceiling_seconds=28,
            expected_max_elapsed_seconds=20.0,
            model_sql=CONFLICTING_FIX_MODEL_SQL,
            expected_exit_code=1,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_large_project_when_checking_native_fixes_then_finishes_within_budget(
    tmp_path: Path,
    test_case: FixPerformanceGuardTestCase,
) -> None:
    project_dir: Path = tmp_path / f"fix_{test_case.model_count}"
    write_lint_performance_project(
        project_dir=project_dir,
        model_count=test_case.model_count,
        model_sql=test_case.model_sql,
    )

    started_at: float = time.perf_counter()
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(Path(sys.executable).with_name("sqb")),
            "--project-dir",
            str(project_dir),
            "--no-color",
            "fix",
            "--check",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=test_case.hard_ceiling_seconds,
    )
    elapsed_seconds: float = time.perf_counter() - started_at
    _LOGGER.info(
        f"native fix models={test_case.model_count} elapsed={elapsed_seconds:.3f}s "
        f"budget={test_case.expected_max_elapsed_seconds:g}s"
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert elapsed_seconds < test_case.expected_max_elapsed_seconds


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [LintPerformanceBehaviorTestCase(description="one selected warm model", expected_maximum=0.25)],
    ids=lambda case: case.description,
)
def test_given_one_selected_model_when_native_linting_warm_then_finishes_under_250ms(
    test_case: LintPerformanceBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    project_dir: Path = tmp_path / "lint_selected"
    write_lint_performance_project(
        project_dir=project_dir,
        model_count=1,
        model_sql=CLEAN_MODEL_SQL,
    )
    arguments: list[str] = [
        "--project-dir",
        str(project_dir),
        "--no-color",
        "lint",
        "--select",
        "model_00000",
    ]
    warmup_exit_code: int = main(arguments)
    assert warmup_exit_code == 0

    started_at: float = time.perf_counter()
    exit_code: int = main(arguments)
    elapsed_seconds: float = time.perf_counter() - started_at

    assert exit_code == 0
    assert elapsed_seconds < test_case.expected_maximum


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        LintPerformanceBehaviorTestCase(
            description="10000 model peak RSS", expected_maximum=500 * 1024
        )
    ],
    ids=lambda case: case.description,
)
def test_given_10000_models_when_native_linting_then_peak_rss_stays_below_budget(
    test_case: LintPerformanceBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    project_dir: Path = tmp_path / "lint_rss_10000"
    write_lint_performance_project(
        project_dir=project_dir,
        model_count=10_000,
        model_sql=CLEAN_MODEL_SQL,
    )
    with tempfile.NamedTemporaryFile() as measurement:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [
                "/usr/bin/time",
                "-f",
                "%M",
                "-o",
                measurement.name,
                str(Path(sys.executable).with_name("sqb")),
                "--project-dir",
                str(project_dir),
                "--no-color",
                "lint",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        measurement.seek(0)
        peak_rss_kib: int = int(measurement.read().decode("utf-8").strip())

    assert result.returncode == 0, result.stdout + result.stderr
    assert peak_rss_kib < test_case.expected_maximum


@pytest.mark.performance
@pytest.mark.parametrize(
    "test_case",
    [
        LintPerformanceBehaviorTestCase(
            description="doubled repeated predicates", expected_maximum=2.5
        )
    ],
    ids=lambda case: case.description,
)
def test_given_doubled_pathological_sql_when_native_linting_then_runtime_scales_boundedly(
    test_case: LintPerformanceBehaviorTestCase,
    tmp_path: Path,
) -> None:
    _ = test_case
    elapsed: list[float] = []
    for predicate_count in (5_000, 10_000):
        project_dir: Path = tmp_path / f"pathological_{predicate_count}"
        write_pathological_lint_project(
            project_dir=project_dir,
            predicate_count=predicate_count,
        )
        started_at: float = time.perf_counter()
        result: subprocess.CompletedProcess[str] = subprocess.run(
            [
                str(Path(sys.executable).with_name("sqb")),
                "--project-dir",
                str(project_dir),
                "--no-color",
                "lint",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        elapsed.append(time.perf_counter() - started_at)
        assert result.returncode == 0, result.stdout + result.stderr

    assert elapsed[1] < elapsed[0] * test_case.expected_maximum
