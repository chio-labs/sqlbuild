from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtDebugCliTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

pytestmark: pytest.MarkDecorator = pytest.mark.dbt

DEBUG_CLI_TEST_CASES: list[DbtDebugCliTestCase] = [
    DbtDebugCliTestCase(
        description="runs dbt and SQLBuild diagnostics",
        command=("dbt", "debug"),
        expected_stdout_fragments=(
            "Running with dbt=",
            "profiles.yml file [",
            "Connection test: [",
            "All checks passed!",
            "SQLBuild Diagnostics",
            "connection test: [OK connected]",
            "query test: [OK SELECT 1]",
        ),
    ),
    DbtDebugCliTestCase(
        description="skips SQLBuild connection when requested",
        command=("dbt", "debug", "--no-connection"),
        expected_stdout_fragments=(
            "Running with dbt=",
            "All checks passed!",
            "SQLBuild Diagnostics",
            "connection test: [SKIP skipped by --no-connection]",
            "query test: [SKIP connection skipped]",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DEBUG_CLI_TEST_CASES,
    ids=[case.description for case in DEBUG_CLI_TEST_CASES],
)
def test_given_dbt_debug_when_running_then_outputs_dbt_and_sqlbuild_diagnostics(
    tmp_path: Path,
    test_case: DbtDebugCliTestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
