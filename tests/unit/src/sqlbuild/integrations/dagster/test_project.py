from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.integrations.dagster import SqlBuildProject, sqlbuild_assets
from sqlbuild.integrations.dagster.exceptions import DagsterProjectPrepareError
from tests.unit.src.sqlbuild.integrations.dagster._test_types import (
    DagsterProjectDecoratorTestCase,
    DagsterProjectPrepareFailureTestCase,
    DagsterProjectPrepareTestCase,
)
from tests.unit.src.sqlbuild.integrations.dagster.helpers import (
    build_dagster_test_dag,
    write_dagster_test_dag,
    write_fake_sqb_command,
)

dg: Any = pytest.importorskip("dagster")


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterProjectPrepareTestCase(
            description="prepare writes dag command output to default artifact path",
            command_stdout=json.dumps(build_dagster_test_dag()),
            expected_dag_contents=json.dumps(build_dagster_test_dag()),
        )
    ],
    ids=["prepare writes dag command output to default artifact path"],
)
def test_given_sqlbuild_project_when_preparing_then_writes_default_dag_artifact(
    test_case: DagsterProjectPrepareTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    expected_dag_path: Path = project_dir / "target" / "sqlbuild_dag.json"
    project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            expected_args=("compile", "--dag", str(expected_dag_path)),
        ),
    )

    project.prepare()

    assert project.dag_path.read_text(encoding="utf-8") == test_case.expected_dag_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterProjectPrepareFailureTestCase(
            description="prepare raises clear error when dag command fails",
            command_stderr="bad dag\n",
            command_exit_code=9,
            expected_error_fragment="SQLBuild DAG preparation failed with exit code 9",
        )
    ],
    ids=["prepare raises clear error when dag command fails"],
)
def test_given_sqlbuild_project_when_prepare_command_fails_then_raises_prepare_error(
    test_case: DagsterProjectPrepareFailureTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    expected_dag_path: Path = project_dir / "target" / "sqlbuild_dag.json"
    project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stderr=test_case.command_stderr,
            exit_code=test_case.command_exit_code,
            expected_args=("compile", "--dag", str(expected_dag_path)),
        ),
    )

    with pytest.raises(DagsterProjectPrepareError) as error:
        project.prepare()

    assert test_case.expected_error_fragment in str(error.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterProjectPrepareTestCase(
            description="prepare if dev writes dag artifact under Dagster dev cli",
            command_stdout=json.dumps(build_dagster_test_dag()),
            expected_dag_contents=json.dumps(build_dagster_test_dag()),
        )
    ],
    ids=["prepare if dev writes dag artifact under Dagster dev cli"],
)
def test_given_dev_cli_environment_when_preparing_if_dev_then_writes_dag_artifact(
    test_case: DagsterProjectPrepareTestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")
    expected_dag_path: Path = project_dir / "target" / "sqlbuild_dag.json"
    project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=write_fake_sqb_command(
            root=tmp_path,
            stdout=test_case.command_stdout,
            expected_args=("compile", "--dag", str(expected_dag_path)),
        ),
    )

    project.prepare_if_dev()

    assert project.dag_path.read_text(encoding="utf-8") == test_case.expected_dag_contents


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterProjectDecoratorTestCase(
            description="decorator loads dag artifact from project default path",
            expected_asset_keys=(
                ("raw", "orders"),
                ("analytics", "customers"),
                ("analytics", "normalize_email"),
                ("analytics", "orders"),
                ("analytics", "waffle_types"),
            ),
        )
    ],
    ids=["decorator loads dag artifact from project default path"],
)
def test_given_sqlbuild_project_when_decorating_assets_then_loads_project_dag_path(
    test_case: DagsterProjectDecoratorTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / "project"
    dag_path: Path = write_dagster_test_dag(root=project_dir / "target")
    project: SqlBuildProject = SqlBuildProject(project_dir=project_dir)

    @sqlbuild_assets(project=project)
    def assets_def() -> dg.MaterializeResult:
        return dg.MaterializeResult()

    assert dag_path == project.dag_path
    assert tuple(sorted(tuple(key.path) for key in assets_def.keys)) == tuple(
        sorted(test_case.expected_asset_keys)
    )
