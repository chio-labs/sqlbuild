from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtScenarioCliTestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    compile_dbt_interop_manifest,
    prepare_dbt_interop_project,
    skip_unless_dbt_is_runnable,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb, table_exists

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtScenarioCliTestCase(
            description="scenario runs with mocked one arg and package-qualified dbt refs",
            command=("--no-color", "scenario", "test", "mocked_dbt_ref_orders"),
            expected_stdout_fragments=(
                "Scenario (1 selected)",
                "mocked_dbt_ref_orders",
                "check     expected mocked_dbt_ref_orders",
                "check     assertion package_ref_joined",
                "PASS=1  FAIL=0  TOTAL=1",
            ),
            expected_absent_relations=("fact_orders",),
        )
    ],
    ids=["scenario runs with mocked one arg and package-qualified dbt refs"],
)
def test_given_dbt_interop_project_when_running_scenario_then_mocks_dbt_refs(
    test_case: DbtScenarioCliTestCase,
    tmp_path: Path,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_interop_project(tmp_path=tmp_path)
    setup_result: subprocess.CompletedProcess[str] = compile_dbt_interop_manifest(
        project_dir=project_dir
    )
    assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    expected_stdout_fragment: str
    for expected_stdout_fragment in test_case.expected_stdout_fragments:
        assert expected_stdout_fragment in result.stdout
    db_path: Path = project_dir / "dbt_interop.duckdb"
    absent_relation: str
    for absent_relation in test_case.expected_absent_relations:
        assert not table_exists(db_path=db_path, table_name=absent_relation)
