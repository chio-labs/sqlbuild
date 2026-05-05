from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.adapters._test_types import (
    ProjectLocalAdapterCliTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.adapters.helpers import (
    prepare_project_with_local_adapter,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectLocalAdapterCliTestCase(
            description="query uses nested project local adapter",
            command=("query", "SELECT 'ignored' AS value", "--format", "csv"),
            expected_stdout_fragment="duckdb_plus",
        )
    ],
    ids=["query uses nested project local adapter"],
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
