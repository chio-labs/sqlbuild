"""E2E tests for the columns scenario fixtures must supply."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.scenario._test_types import (
    ScenarioInlineProjectE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.scenario.helpers import (
    build_lambda_scenario_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    (
        ScenarioInlineProjectE2ETestCase(
            description="lambda parameters are not mock columns",
            repo_files=build_lambda_scenario_project_files(),
            command=("--no-color", "scenario", "test"),
            expected_exit_code=0,
            expected_stdout_fragments=("PASS=1  FAIL=0  TOTAL=1",),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_scenario_fixture_when_running_cli_then_requires_only_real_columns(
    test_case: ScenarioInlineProjectE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path, project_name="fixture_columns", repo_files=test_case.repo_files
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert all(fragment in result.stdout for fragment in test_case.expected_stdout_fragments)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
