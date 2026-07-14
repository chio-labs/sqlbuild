from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.classes.dbt_runner import DbtRunner
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtCommandResult, DbtLsResult
from tests.integration.src.sqlbuild.integrations.dbt._test_types import RealDbtRunnerTestCase

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtRunnerTestCase(
            description="lists all project models",
            select=(),
            exclude=(),
            resource_types=("model",),
            expected_unique_ids=("model.analytics.fact_orders", "model.analytics.stg_orders"),
        ),
        RealDbtRunnerTestCase(
            description="honors tag selector and exclude",
            select=("tag:nightly",),
            exclude=("fact_orders",),
            resource_types=("model",),
            expected_unique_ids=("model.analytics.stg_orders",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_real_dbt_project_when_running_ls_then_returns_manifest_unique_ids(
    test_case: RealDbtRunnerTestCase,
    real_dbt_executable: str,
    dbt_project_dir: Path,
    dbt_profiles_dir: Path,
) -> None:
    options: DbtCliOptions = DbtCliOptions(
        project_dir=dbt_project_dir,
        profiles_dir=dbt_profiles_dir,
        target_path=dbt_project_dir / "target",
    )
    runner: DbtRunner = DbtRunner(dbt_executable=real_dbt_executable)

    compile_result: DbtCommandResult = runner.compile(options=options)
    result: DbtLsResult = runner.ls(
        options=options,
        select=test_case.select,
        exclude=test_case.exclude,
        resource_types=test_case.resource_types,
    )

    assert compile_result.returncode == 0, compile_result.stderr or compile_result.stdout
    assert result.command.returncode == 0, result.command.stderr or result.command.stdout
    assert tuple(sorted(node.unique_id for node in result.nodes)) == tuple(
        sorted(test_case.expected_unique_ids)
    )
    assert (dbt_project_dir / "target" / "manifest.json").exists()
