from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.query._test_types import (
    QueryCliTestCase,
    QueryFileCliTestCase,
    QueryFileErrorCliTestCase,
)
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


@pytest.mark.parametrize(
    "test_case",
    [
        QueryFileCliTestCase(
            description="executes UTF-8 SQL from a file relative to the working directory",
            query_file_path="queries/orders.sql",
            query_sql="SELECT 7 AS order_id, 'gaufre' AS label\n",
            expected_stdout_fragment=(
                "-[ RECORD 1 ]---------------------------+\n"
                "order_id | 7\n"
                "label    | gaufre\n\n"
                "1 row\n"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_query_file_when_running_query_then_executes_file_contents(
    tmp_path: Path,
    test_case: QueryFileCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="query_file_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "query_file_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "query.duckdb"\n'
            ),
            test_case.query_file_path: test_case.query_sql,
        },
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("query", "--file", test_case.query_file_path),
        project_dir=project_dir,
        working_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr
    assert test_case.expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    (
        QueryFileErrorCliTestCase(
            description="rejects inline SQL together with a query file",
            command=("query", "SELECT 1 AS inline_id", "--file", "queries/orders.sql"),
            repo_files={"queries/orders.sql": "SELECT 2 AS file_id\n"},
            expected_stderr_fragment=(
                "error[C104]: query accepts either positional SQL or --file, not both"
            ),
        ),
        QueryFileErrorCliTestCase(
            description="reports a missing query file",
            command=("query", "--file", "queries/missing.sql"),
            expected_stderr_fragment=(
                "error[C105]: query file does not exist: queries/missing.sql"
            ),
        ),
        QueryFileErrorCliTestCase(
            description="rejects a directory as a query file",
            command=("query", "--file", "queries"),
            repo_files={"queries/orders.sql": "SELECT 1 AS order_id\n"},
            expected_stderr_fragment=("error[C106]: query file path is not a file: queries"),
        ),
        QueryFileErrorCliTestCase(
            description="rejects query files that are not UTF-8",
            command=("query", "--file", "queries/invalid.sql"),
            binary_files={"queries/invalid.sql": b"\xff\xfe\x00"},
            expected_stderr_fragment=(
                "error[C107]: query file could not be read as UTF-8: queries/invalid.sql"
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_invalid_query_file_input_when_running_query_then_reports_actionable_error(
    tmp_path: Path,
    test_case: QueryFileErrorCliTestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="query_file_error_project",
        repo_files={
            "sqlbuild_project.toml": (
                'name = "query_file_error_project"\nadapter = "duckdb"\n\n'
                '[connection]\ndatabase = "query.duckdb"\n'
            ),
            **test_case.repo_files,
        },
    )
    for relative_path, contents in test_case.binary_files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(contents)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        working_dir=project_dir,
    )

    assert result.returncode == 1
    assert test_case.expected_stderr_fragment in result.stderr
