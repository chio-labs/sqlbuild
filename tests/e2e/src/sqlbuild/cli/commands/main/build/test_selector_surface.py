"""E2E tests for selector surface behavior through the CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    SelectorSurfaceBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_waffle_shop,
    run_sqb,
)

TEST_CASES: list[SelectorSurfaceBuildE2ETestCase] = [
    SelectorSurfaceBuildE2ETestCase(
        description="slash path selector works on build",
        command=("--no-color", "build", "--select", "/marts"),
        expected_exit_code=0,
        expected_fragments=("Plan ready (10 selected)", "hourly_activity_with_daily_context"),
        expected_stream="stdout",
        pre_commands=(("--no-color", "build"),),
    ),
    SelectorSurfaceBuildE2ETestCase(
        description="path selector endpoint expansion works on build",
        command=("--no-color", "build", "--select", "+fact_orders~daily_activity_rollup+"),
        expected_exit_code=0,
        expected_fragments=(
            "Plan ready (9 selected, 1 source to load)",
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
        expected_stream="stdout",
        pre_commands=(("--no-color", "build"),),
    ),
    SelectorSurfaceBuildE2ETestCase(
        description="malformed path selector with internal plus fails clearly",
        command=("--no-color", "plan", "--select", "+fact_orders~+daily_activity_rollup"),
        expected_exit_code=1,
        expected_fragments=("contains '+' in an unsupported position",),
        expected_stream="stderr",
    ),
    SelectorSurfaceBuildE2ETestCase(
        description="malformed path selector missing rhs fails clearly",
        command=("--no-color", "plan", "--select", "fact_orders~"),
        expected_exit_code=1,
        expected_fragments=("requires names on both sides of '~'",),
        expected_stream="stderr",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
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
    rendered: str = result.stdout if test_case.expected_stream == "stdout" else result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in rendered, result.stdout + result.stderr
