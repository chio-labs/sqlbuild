from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clone._test_types import CloneE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        CloneE2ETestCase(
            description="clone blocks in virtual mode",
            repo_files={
                "sqlbuild_project.toml": dedent(
                    """
                    name = "virtual_clone_project"
                    adapter = "duckdb"
                    environment_mode = "virtual"
                    default_environment = "dev"

                    [environments.prod]
                    schema = "prod"

                    [environments.prod.clone]
                    allow_as_source = true
                    allow_as_target = false

                    [environments.dev]
                    schema = "dev"

                    [environments.dev.clone]
                    allow_as_source = true
                    allow_as_target = true
                    """
                ).strip()
                + "\n"
            },
            clone_command=("--no-color", "clone", "--from", "prod", "--to", "dev"),
            expected_exit_code=1,
            expected_stdout_fragments=(),
            expected_query_results=(),
        )
    ],
    ids=["clone blocks in virtual mode"],
)
def test_given_virtual_mode_project_when_running_clone_then_cli_blocks_cleanly(
    test_case: CloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_clone_project",
        repo_files=test_case.repo_files,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.clone_command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert "clone is not supported when environment_mode = 'virtual'" in result.stderr
