from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.run._test_types import RunE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import prepare_inline_project, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        RunE2ETestCase(
            description="run blocks in virtual mode",
            expected_exit_code=1,
            expected_table_names=(),
            expected_view_names=(),
        )
    ],
    ids=["run blocks in virtual mode"],
)
def test_given_virtual_mode_project_when_running_run_then_cli_blocks_cleanly(
    test_case: RunE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_run_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "virtual_run_project"\nadapter = "duckdb"\nenvironment_mode = "virtual"\n'
            )
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "run"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert "run is not supported when environment_mode = 'virtual'" in result.stderr
