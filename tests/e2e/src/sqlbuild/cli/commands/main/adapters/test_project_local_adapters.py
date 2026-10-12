from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.adapters._test_types import (
    ProjectLocalAdapterCliTestCase,
    ProjectLocalRenderingTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.adapters.helpers import (
    prepare_project_with_local_adapter,
    prepare_project_with_rendering_adapter,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import query_duckdb, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectLocalAdapterCliTestCase(
            description="query uses nested project local adapter",
            command=("query", "SELECT 'ignored' AS value", "--format", "csv"),
            expected_stdout_fragment="duckdb_plus",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_local_adapter_when_running_query_then_uses_local_adapter(
    tmp_path: Path,
    test_case: ProjectLocalAdapterCliTestCase,
) -> None:
    project_dir: Path = prepare_project_with_local_adapter(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_return_code, result.stdout + result.stderr
    assert test_case.expected_stdout_fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectLocalRenderingTestCase(
            description="table DDL comes from the overriding project local adapter",
            expected_marker_rows=[(1,)],
            expected_model_rows=[(1, "shipped")],
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_local_rendering_override_when_building_then_override_renders_ddl(
    tmp_path: Path,
    test_case: ProjectLocalRenderingTestCase,
) -> None:
    project_dir: Path = prepare_project_with_rendering_adapter(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir, working_dir=project_dir
    )

    assert result.returncode == 0, result.stdout + result.stderr
    database: Path = project_dir / "local.duckdb"
    assert (
        query_duckdb(db_path=database, sql="SELECT marked FROM main.rendering_override_marker")
        == test_case.expected_marker_rows
    )
    assert (
        query_duckdb(db_path=database, sql="SELECT order_id, status FROM main.orders")
        == test_case.expected_model_rows
    )
