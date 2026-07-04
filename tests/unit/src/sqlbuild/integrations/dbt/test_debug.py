from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.models import DbtCommandResult
from sqlbuild.integrations.dbt.pipeline.main.debug import debug_dbt_from_project
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtDebugPipelineTestCase
from tests.unit.src.sqlbuild.integrations.dbt.helpers import RecordingDbtInvoker


@pytest.mark.parametrize(
    "test_case",
    (
        DbtDebugPipelineTestCase(
            description="runs dbt debug with resolved config and strips SQLBuild local args",
            args=(
                "--project-dir",
                "../dbt_project",
                "--profiles-dir",
                "../profiles",
                "--target",
                "dev",
                "--target-path",
                "../target/dbt",
                "--no-connection",
                "--connection",
            ),
            expected_argv=(
                "dbt",
                "debug",
                "--project-dir",
                "{dbt_project}",
                "--profiles-dir",
                "{profiles}",
                "--target",
                "dev",
                "--connection",
            ),
            expected_stdout="dbt ok\n",
            expected_stderr="dbt warn\n",
            expected_returncode=0,
        ),
        DbtDebugPipelineTestCase(
            description="uses local dbt target when cli target is absent",
            args=(
                "--project-dir",
                "../dbt_project",
                "--profiles-dir",
                "../profiles",
            ),
            expected_argv=(
                "dbt",
                "debug",
                "--project-dir",
                "{dbt_project}",
                "--profiles-dir",
                "{profiles}",
                "--target",
                "pat",
            ),
            expected_stdout="dbt ok\n",
            expected_stderr="dbt warn\n",
            expected_returncode=0,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_dbt_debug_args_when_running_pipeline_then_invokes_only_dbt_debug(
    tmp_path: Path,
    test_case: DbtDebugPipelineTestCase,
) -> None:
    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    dbt_project_dir: Path = tmp_path / "dbt_project"
    profiles_dir: Path = tmp_path / "profiles"
    sqlbuild_project_dir.mkdir()
    dbt_project_dir.mkdir()
    profiles_dir.mkdir()
    sqlbuild_project_dir.joinpath("sqlbuild_project.toml").write_text(
        'name = "debug_pipeline"\nadapter = "duckdb"\n[dbt]\ntarget = "dev"\n',
        encoding="utf-8",
    )
    sqlbuild_project_dir.joinpath("sqlbuild_local.toml").write_text(
        '[dbt]\ntarget = "pat"\n',
        encoding="utf-8",
    )
    expected_argv: tuple[str, ...] = tuple(
        value.format(
            dbt_project=dbt_project_dir,
            profiles=profiles_dir,
        )
        for value in test_case.expected_argv
    )
    invoker: RecordingDbtInvoker = RecordingDbtInvoker(
        DbtCommandResult(
            argv=expected_argv,
            returncode=test_case.expected_returncode,
            stdout=test_case.expected_stdout,
            stderr=test_case.expected_stderr,
        )
    )
    stdout_stream: StringIO = StringIO()
    stderr_stream: StringIO = StringIO()

    returncode: int = debug_dbt_from_project(
        project_dir=sqlbuild_project_dir,
        args=test_case.args,
        dbt_runner=DbtRunner(dbt_executable="dbt", invoker=invoker),
        stdout_stream=stdout_stream,
        stderr_stream=stderr_stream,
    )

    assert returncode == test_case.expected_returncode
    assert invoker.calls == [(expected_argv, dbt_project_dir)]
    assert stdout_stream.getvalue() == test_case.expected_stdout
    assert stderr_stream.getvalue() == test_case.expected_stderr
