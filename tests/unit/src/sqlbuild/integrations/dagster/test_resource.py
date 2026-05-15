from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sqlbuild.integrations.dagster import SqlBuildCliResource
from sqlbuild.integrations.dagster.helpers.invocation import SqlBuildCliInvocation
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterCliFailureTestCase,
    DagsterCliInvocationTestCase,
    DagsterCliStreamTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    write_dagster_test_dag,
    write_fake_sqb_command,
)

dg: Any = pytest.importorskip("dagster")

CLI_INVOCATION_TEST_CASES: list[DagsterCliInvocationTestCase] = [
    DagsterCliInvocationTestCase(
        description="wait captures successful command output",
        command_stdout="built ok\n",
        command_stderr="warning line\n",
        command_exit_code=0,
        expected_success=True,
        expected_stdout="built ok\n",
        expected_stderr="warning line\n",
    ),
    DagsterCliInvocationTestCase(
        description="wait captures failing command output without raising when disabled",
        command_stdout="",
        command_stderr="boom\n",
        command_exit_code=7,
        expected_success=False,
        expected_stdout="",
        expected_stderr="boom\n",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    CLI_INVOCATION_TEST_CASES,
    ids=[case.description for case in CLI_INVOCATION_TEST_CASES],
)
def test_given_sqlbuild_cli_resource_when_waiting_invocation_then_captures_process_result(
    test_case: DagsterCliInvocationTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
    )

    invocation: SqlBuildCliInvocation = resource.cli(["build"], raise_on_error=False).wait()

    assert invocation.is_successful() is test_case.expected_success
    assert invocation.stdout == test_case.expected_stdout
    assert invocation.stderr == test_case.expected_stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliStreamTestCase(
            description="stream yields materialize results for dag assets",
            command_stdout="built ok\n",
            command_exit_code=0,
            expected_asset_keys=(
                ("raw", "orders"),
                ("analytics", "normalize_email"),
                ("analytics", "orders"),
            ),
        )
    ],
    ids=["stream yields materialize results for dag assets"],
)
def test_given_sqlbuild_cli_resource_with_dag_when_streaming_then_yields_asset_results(
    test_case: DagsterCliStreamTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            exit_code=test_case.command_exit_code,
        ),
        dag_path=str(write_dagster_test_dag(root=tmp_path)),
    )

    results: list[Any] = list(resource.cli(["build"]).stream())

    assert (
        tuple(tuple(result.asset_key.path) for result in results) == test_case.expected_asset_keys
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterCliFailureTestCase(
            description="wait raises Dagster failure for nonzero command",
            command_stderr="build failed\n",
            command_exit_code=3,
            expected_error_fragment="SQLBuild CLI command failed with exit code 3",
        )
    ],
    ids=["wait raises Dagster failure for nonzero command"],
)
def test_given_sqlbuild_cli_resource_when_waiting_failed_invocation_then_raises_failure(
    test_case: DagsterCliFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    resource: SqlBuildCliResource = SqlBuildCliResource(
        project_dir=str(project_dir),
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
        ),
    )

    with pytest.raises(dg.Failure) as error:
        resource.cli(["build"]).wait()

    assert test_case.expected_error_fragment in str(error.value)
