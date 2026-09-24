"""E2E tests for SQL tests of models that use `__cursor_start()` and `__cursor_end()`."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import CursorWindowE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    CURSOR_WINDOW_PASSING_TESTS,
    build_cursor_window_project_files,
    build_declared_window_test,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_DECLARED_ERROR_PREFIX: str = (
    "SQL test 'declared_window_case' in 'tests/unit/declared_window_case.sql'"
)


@pytest.mark.parametrize(
    "test_case",
    (
        CursorWindowE2ETestCase(
            description="default and declared windows evaluate intrinsic models",
            tests=CURSOR_WINDOW_PASSING_TESTS,
            expected_exit_code=0,
            expected_output_fragments=("PASS=6  FAIL=0  TOTAL=6",),
            expected_compiled_fragments=(
                "TIMESTAMP '1900-01-01 00:00:00'",
                "TIMESTAMP '2999-12-31 00:00:00'",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_models_using_cursor_intrinsics_when_testing_then_window_is_rendered(
    test_case: CursorWindowE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="cursor_window_project",
        repo_files=build_cursor_window_project_files(tests=test_case.tests),
    )
    test_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "test"), project_dir=project_dir
    )
    compile_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile"), project_dir=project_dir
    )

    output: str = test_result.stdout + test_result.stderr
    assert test_result.returncode == test_case.expected_exit_code, output
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output
    assert compile_result.returncode == 0, compile_result.stdout + compile_result.stderr
    runtime_sql: str = next(
        (project_dir / "target" / "run" / "tests").rglob("default_window_keeps_every_row.sql")
    ).read_text(encoding="utf-8")
    compiled_sql: str = next(
        (project_dir / "target" / "compiled" / "tests").rglob("default_window_keeps_every_row.sql")
    ).read_text(encoding="utf-8")
    assert runtime_sql == compiled_sql
    assert "__cursor_start" not in compiled_sql, compiled_sql
    for fragment in test_case.expected_compiled_fragments:
        assert fragment in compiled_sql, compiled_sql
    declared_sql: str = next(
        (project_dir / "target" / "compiled" / "tests").rglob(
            "declared_window_excludes_rows_outside.sql"
        )
    ).read_text(encoding="utf-8")
    assert "TIMESTAMP '2026-02-01'" in declared_sql, declared_sql
    assert "TIMESTAMP '2026-02-03'" in declared_sql, declared_sql


@pytest.mark.parametrize(
    "test_case",
    (
        CursorWindowE2ETestCase(
            description="inverted declared window",
            tests=build_declared_window_test(
                window='cursor_start "2026-02-03", cursor_end "2026-02-01"',
                model_name="daily_orders",
            ),
            expected_exit_code=1,
            expected_output_fragments=(
                (
                    _DECLARED_ERROR_PREFIX
                    + ": cursor_start '2026-02-03' must be before the exclusive cursor_end "
                    "'2026-02-01' for model 'daily_orders'"
                ),
            ),
        ),
        CursorWindowE2ETestCase(
            description="invalid timestamp bound",
            tests=build_declared_window_test(
                window='cursor_start "first of february"',
                model_name="daily_orders",
            ),
            expected_exit_code=1,
            expected_output_fragments=(
                (
                    _DECLARED_ERROR_PREFIX
                    + ": cursor_start 'first of february' must be an ISO timestamp or date "
                    "because model 'daily_orders' uses cursor_type timestamp"
                ),
            ),
        ),
        CursorWindowE2ETestCase(
            description="bound not aligned to the model grain",
            tests=build_declared_window_test(
                window='cursor_end "2026-02-03 12:00:00"',
                model_name="daily_orders",
            ),
            expected_exit_code=1,
            expected_output_fragments=(
                (
                    _DECLARED_ERROR_PREFIX
                    + ": cursor_end '2026-02-03 12:00:00' is not aligned to cursor_grain day of "
                    "model 'daily_orders'"
                ),
            ),
        ),
        CursorWindowE2ETestCase(
            description="timestamp bound for an integer cursor",
            tests=build_declared_window_test(
                window='cursor_start "2026-02-01"',
                model_name="event_totals",
            ),
            expected_exit_code=1,
            expected_output_fragments=(
                (
                    _DECLARED_ERROR_PREFIX
                    + ": cursor_start '2026-02-01' must be an integer because model "
                    "'event_totals' uses cursor_type integer"
                ),
            ),
        ),
        CursorWindowE2ETestCase(
            description="declared window without an intrinsic model",
            tests=build_declared_window_test(
                window='cursor_start "2026-02-01"', model_name="plain_orders"
            ),
            expected_exit_code=1,
            expected_output_fragments=(
                (
                    _DECLARED_ERROR_PREFIX
                    + " declares cursor_start or cursor_end, but no model it evaluates uses "
                    "__cursor_start() or __cursor_end()"
                ),
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_declared_cursor_window_when_testing_and_compiling_then_errors_clearly(
    test_case: CursorWindowE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="cursor_window_error_project",
        repo_files=build_cursor_window_project_files(tests=test_case.tests),
    )

    results: tuple[subprocess.CompletedProcess[str], ...] = tuple(
        run_sqb(command=command, project_dir=project_dir)
        for command in (("--no-color", "test"), ("--no-color", "compile"))
    )

    for result in results:
        output: str = result.stdout + result.stderr
        assert result.returncode == test_case.expected_exit_code, output
        for fragment in test_case.expected_output_fragments:
            assert fragment in output, output
        assert "Connecting to" not in output, output
