"""E2E tests for selector surface behavior through the CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    SelectorSurfaceBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_waffle_shop,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SelectorSurfaceBuildE2ETestCase(
            description="slash path selector works on build",
            command=("--no-color", "build", "--select", "/models/marts"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Plan ready  10 selected",
                "hourly_activity_with_daily_context",
            ),
            expected_stderr_fragments=(),
            pre_commands=(("--no-color", "build"),),
        ),
        SelectorSurfaceBuildE2ETestCase(
            description="path selector endpoint expansion works on build",
            command=(
                "--no-color",
                "build",
                "--select",
                "+fact_orders~daily_activity_rollup+",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Plan ready  9 selected, 1 source to load",
                "Sources to load (1)",
                "raw_orders",
                "waffle_types",
                "stg_orders",
                "stg_payments",
                "fact_orders",
                "hourly_order_activity",
                "daily_activity_rollup",
                "hourly_activity_with_daily_context",
            ),
            expected_stderr_fragments=(),
            pre_commands=(("--no-color", "build"),),
        ),
        SelectorSurfaceBuildE2ETestCase(
            description="malformed path selector with internal plus fails clearly",
            command=("--no-color", "plan", "--select", "+fact_orders~+daily_activity_rollup"),
            expected_exit_code=1,
            expected_stdout_fragments=(),
            expected_stderr_fragments=("contains '+' in an unsupported position",),
        ),
        SelectorSurfaceBuildE2ETestCase(
            description="malformed path selector missing rhs fails clearly",
            command=("--no-color", "plan", "--select", "fact_orders~"),
            expected_exit_code=1,
            expected_stdout_fragments=(),
            expected_stderr_fragments=("requires names on both sides of '~'",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_selector_commands_when_running_cli_then_behavior_matches_expectation(
    test_case: SelectorSurfaceBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    pre_command: tuple[str, ...]
    for pre_command in test_case.pre_commands:
        initial_result: subprocess.CompletedProcess[str] = run_sqb(
            command=pre_command,
            project_dir=project_dir,
        )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout, result.stdout + result.stderr
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr, result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        SelectorSurfaceBuildE2ETestCase(
            description="verbose selector file reports resolved context without secrets",
            command=("--no-color", "build", "--verbose"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Execution\n  command      sqb build",
                "run_id       ",
                "target       not set",
                "warehouse    not set",
                "concurrency  1 configured limit",
                "full_refresh false",
                "selected     1 of 17 managed resources",
                "date vars    1970-01-01 to 2030-12-31",
                "Selection files",
                "(1 selector)",
            ),
            expected_stderr_fragments=(),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_verbose_build_selector_file_when_running_then_reports_safe_resolved_context(
    test_case: SelectorSurfaceBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    selector_file: Path = tmp_path / "dagster-selectors.txt"
    selector_file.write_text("+stg_customers\n", encoding="utf-8")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            *test_case.command,
            "--select-file",
            str(selector_file),
            "--vars",
            '{"start_date":"1970-01-01","end_date":"2030-12-31","api_secret":"never-print-secret"}',
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert f"selector_file {selector_file} (1 selector)" in result.stdout
    assert "never-print-secret" not in result.stdout
    assert "never-print-secret" not in result.stderr
