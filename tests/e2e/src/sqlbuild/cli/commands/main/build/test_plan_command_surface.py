"""E2E tests for focused plan command surface behavior."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    PlanCommandBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_waffle_shop, run_sqb

TEST_CASES: list[PlanCommandBuildE2ETestCase] = [
    PlanCommandBuildE2ETestCase(
        description="plan select no-color scopes to marts",
        command=("--no-color", "plan", "--select", "path:marts"),
        expected_exit_code=0,
        expected_fragments=(
            "Plan ready (10 selected)",
            "Functions (2 standard run)",
            "is_completed_order",
            "sql udf",
            "is_completed_order_py",
            "python udf",
            "Models (8 standard run)",
        ),
        expected_stream="stdout",
    ),
    PlanCommandBuildE2ETestCase(
        description="plan exclude removes marts branch from selected scope",
        command=("--no-color", "plan", "--select", "/marts", "--exclude", "hourly_order_activity"),
        expected_exit_code=0,
        expected_fragments=(
            "Plan ready (9 selected)",
            "Functions (2 standard run)",
            "Models (7 standard run)",
        ),
        expected_stream="stdout",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_plan_command_variants_when_running_cli_then_scope_behavior_matches_expectation(
    test_case: PlanCommandBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    initial_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    assert initial_build_result.returncode == 0, (
        initial_build_result.stdout + initial_build_result.stderr
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )
    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    rendered: str = result.stdout if test_case.expected_stream == "stdout" else result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in rendered, result.stdout + result.stderr
