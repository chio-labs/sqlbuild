"""E2E tests for executing SQLBuild through Dagster assets."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from dagster import AssetExecutionContext, ExecuteInProcessResult, materialize

from sqlbuild.integrations.dagster import SqlBuildCliResource, SqlBuildProject, sqlbuild_assets
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    REPO_ROOT,
    prepare_waffle_shop,
    table_exists,
)
from tests.e2e.src.sqlbuild.integrations.dagster._test_types import (
    DagsterSqlBuildE2ETestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DagsterSqlBuildE2ETestCase(
            description="dagster loads generated dag artifact and executes sqlbuild build",
            expected_success=True,
            expected_dag_artifact="target/sqlbuild_dag.json",
            expected_table_names=("fact_orders", "dim_customers", "waffle_types"),
            expected_asset_keys=(
                ("raw_orders",),
                ("main", "waffle_types"),
                ("main", "is_completed_order"),
                ("main", "fact_orders"),
            ),
        )
    ],
    ids=["dagster loads generated dag artifact and executes sqlbuild build"],
)
def test_given_waffle_shop_when_executing_sqlbuild_assets_then_dagster_run_succeeds(
    test_case: DagsterSqlBuildE2ETestCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    sqb_executable: Path = REPO_ROOT / ".venv" / "bin" / "sqb"
    sqlbuild_project: SqlBuildProject = SqlBuildProject(
        project_dir=project_dir,
        sqb_command=(str(sqb_executable),),
    )
    monkeypatch.setenv("DAGSTER_IS_DEV_CLI", "1")

    sqlbuild_project.prepare_if_dev()

    @sqlbuild_assets(project=sqlbuild_project, required_resource_keys={"sqb"})
    def sqlbuild_waffle_shop(context: AssetExecutionContext) -> Iterator[object]:
        yield from context.resources.sqb.cli(["build"], context=context).stream()

    result: ExecuteInProcessResult = materialize(
        [sqlbuild_waffle_shop],
        resources={"sqb": SqlBuildCliResource(project_dir=sqlbuild_project)},
    )

    assert result.success is test_case.expected_success
    assert sqlbuild_project.dag_path == project_dir / test_case.expected_dag_artifact
    assert sqlbuild_project.dag_path.exists()
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=project_dir / "waffle_shop.duckdb", table_name=table_name)
    assert set(test_case.expected_asset_keys) <= {
        tuple(asset_key.path) for asset_key in sqlbuild_waffle_shop.keys
    }
