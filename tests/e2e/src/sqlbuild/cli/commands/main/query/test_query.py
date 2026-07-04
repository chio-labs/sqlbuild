from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.query._test_types import QueryCliTestCase
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        QueryCliTestCase(
            description="renders long output with default limit",
            command=("query", "SELECT 1 AS id, 'alice' AS name"),
            expected_stdout_fragment=(
                "-[ RECORD 1 ]---------------------------+\nid   | 1\nname | alice\n\n1 row\n"
            ),
        ),
        QueryCliTestCase(
            description="renders table output when requested",
            command=("query", "SELECT 1 AS id", "--format", "table"),
            expected_stdout_fragment="id\n--\n1\n\n1 row\n",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_query_command_when_running_then_outputs_result(
    tmp_path: Path,
    test_case: QueryCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="query_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "query_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "query.duckdb"\n'
            ),
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_returncode, result.stderr
    assert test_case.expected_stdout_fragment in result.stdout
