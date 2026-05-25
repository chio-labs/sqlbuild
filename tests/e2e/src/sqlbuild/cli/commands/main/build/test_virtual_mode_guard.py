from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    VirtualModeGuardBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project, run_sqb

TEST_CASES: list[VirtualModeGuardBuildE2ETestCase] = [
    VirtualModeGuardBuildE2ETestCase(
        description="plan blocks defer-to in virtual mode",
        project_toml=dedent(
            """
            name = "virtual_plan_project"
            adapter = "duckdb"
            environment_mode = "virtual"
            default_environment = "dev"

            [environments.dev]
            schema = "dev"

            [environments.prod]
            schema = "prod"
            """
        ).strip()
        + "\n",
        command=("--no-color", "plan", "--defer-to", "prod"),
        expected_exit_code=1,
        expected_error_fragment=(
            "plan does not support --defer-to when environment_mode = 'virtual'"
        ),
    ),
    VirtualModeGuardBuildE2ETestCase(
        description="build blocks defer-to in virtual mode",
        project_toml=dedent(
            """
            name = "virtual_build_project"
            adapter = "duckdb"
            environment_mode = "virtual"
            default_environment = "dev"

            [environments.dev]
            schema = "dev"

            [environments.prod]
            schema = "prod"
            """
        ).strip()
        + "\n",
        command=("--no-color", "build", "--defer-to", "prod"),
        expected_exit_code=1,
        expected_error_fragment=(
            "build does not support --defer-to when environment_mode = 'virtual'"
        ),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_virtual_mode_defer_to_when_running_cli_then_blocks_cleanly(
    test_case: VirtualModeGuardBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_mode_guard_project",
        repo_files={"sqlbuild_project.toml": test_case.project_toml},
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert test_case.expected_error_fragment in result.stderr
