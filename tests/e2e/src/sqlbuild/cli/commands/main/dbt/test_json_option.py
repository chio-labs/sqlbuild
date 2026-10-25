"""E2E coverage that `sqb dbt run` and `sqb dbt build` reject `--json`, which they cannot honour."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtJsonOptionE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import prepare_dbt_interop_project
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        DbtJsonOptionE2ETestCase(
            description="dbt run rejects --json",
            command=("dbt", "run", "--json", "--select", "local_only"),
            expected_returncode=1,
            expected_stderr_fragment="error[C238]: sqb dbt run does not support --json",
        ),
        DbtJsonOptionE2ETestCase(
            description="dbt build rejects a leading global --json",
            command=("--json", "dbt", "build"),
            expected_returncode=1,
            expected_stderr_fragment="error[C238]: sqb dbt build does not support --json",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_json_option_when_running_dbt_interop_then_it_is_rejected_before_dbt_runs(
    test_case: DbtJsonOptionE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command, project_dir=project_dir
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    assert test_case.expected_stderr_fragment in result.stderr, test_case.description
    assert "sqb dbt plan --json" in result.stderr
    assert not (project_dir / "dbt_interop.duckdb").exists()
