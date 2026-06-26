from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtCloneE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    drop_dbt_clone_origin_orders_relation,
    prepare_dbt_diff_workspace,
    skip_unless_dbt_is_runnable,
    write_dbt_clone_summary_view_model,
    write_dbt_diff_orders_model,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    query_duckdb,
    run_sqb,
    table_exists,
)

pytestmark: pytest.MarkDecorator = pytest.mark.dbt

CLONE_ERROR_E2E_TEST_CASES: tuple[DbtCloneE2ETestCase, ...] = (
    DbtCloneE2ETestCase(
        description="missing production_ref config explains how to configure clone",
        command=("dbt", "clone", "--select", "dbt_orders"),
        expected_returncode=1,
        expected_stderr_fragments=(
            "dbt clone requires [dbt.production_ref] to be configured",
            "sqb dbt init",
        ),
        include_production_ref=False,
    ),
    DbtCloneE2ETestCase(
        description="empty clone selection explains how to select models",
        command=("dbt", "clone", "--select", "does_not_exist"),
        expected_returncode=1,
        expected_stderr_fragments=(
            "dbt clone selected no dbt models",
            "Use --select to choose at least one dbt model.",
        ),
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneE2ETestCase(
            description="dbt clone copies production table into current target",
            command=("--no-color", "dbt", "clone", "--select", "dbt_orders", "--hard-copy"),
            expected_returncode=0,
            expected_stdout_fragments=(
                "dbt_orders",
                "copied",
                "1/1",
                "Completed successfully.",
                "COPIED=1",
            ),
            expected_stderr_fragments=(
                "Compiling dbt project...",
                "Compiling dbt production ref git ref 'prod'...",
                "Resolving dbt selection...",
            ),
            expected_rows=((1, 900), (2, 900)),
            rows_sql="SELECT order_id, amount_cents FROM main.dbt_orders ORDER BY order_id",
        )
    ],
    ids=["dbt clone copies production table into current target"],
)
def test_given_changed_current_model_when_cloning_then_copies_prod_relation(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="clone_workspace",
    )
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=111,
        order_ids=(1, 3),
        include_unique_key=True,
        include_cursor_meta=True,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr
    assert (
        tuple(
            query_duckdb(
                db_path=workspace / "warehouse.duckdb",
                sql=test_case.rows_sql,
            )
        )
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneE2ETestCase(
            description="dbt clone recreates selected view from current SQL",
            command=("--no-color", "dbt", "clone", "--select", "dbt_order_summary"),
            expected_returncode=0,
            expected_stdout_fragments=(
                "dbt_order_summary",
                "recreated_view",
                "RECREATED_VIEWS=1",
            ),
            expected_rows=((111,),),
            rows_sql="SELECT total_amount_cents FROM main.dbt_order_summary",
        )
    ],
    ids=["dbt clone recreates selected view from current SQL"],
)
def test_given_view_model_when_cloning_then_recreates_current_view_sql(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="clone_view_workspace",
        include_view_model=True,
    )
    write_dbt_clone_summary_view_model(workspace=workspace, amount_cents=111)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert (
        tuple(query_duckdb(db_path=workspace / "warehouse.duckdb", sql=test_case.rows_sql))
        == test_case.expected_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneE2ETestCase(
            description="dbt clone honors multi select and exclude",
            command=(
                "--no-color",
                "dbt",
                "clone",
                "--select",
                "dbt_orders",
                "dbt_customers",
                "--exclude",
                "dbt_customers",
                "--hard-copy",
            ),
            expected_returncode=0,
            expected_stdout_fragments=("dbt_orders", "COPIED=1", "TOTAL=1"),
            expected_absent_stdout_fragments=("dbt_customers",),
            expected_rows=((1, 900), (2, 900)),
            expected_absent_relations=(("main", "dbt_customers"),),
        )
    ],
    ids=["dbt clone honors multi select and exclude"],
)
def test_given_multi_select_with_exclude_when_cloning_then_only_selected_models_clone(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="clone_selection_workspace",
        include_second_model=True,
    )
    write_dbt_diff_orders_model(
        workspace=workspace,
        amount_cents=111,
        order_ids=(1, 3),
        include_unique_key=True,
        include_cursor_meta=True,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    for fragment in test_case.expected_absent_stdout_fragments:
        assert fragment not in result.stdout
    assert (
        tuple(query_duckdb(db_path=workspace / "warehouse.duckdb", sql=test_case.rows_sql))
        == test_case.expected_rows
    )
    absent_relation: tuple[str, str]
    for absent_relation in test_case.expected_absent_relations:
        assert not table_exists(
            db_path=workspace / "warehouse.duckdb",
            schema=absent_relation[0],
            table_name=absent_relation[1],
        )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtCloneE2ETestCase(
            description="dbt clone warns when origin warehouse relation is missing",
            command=("--no-color", "dbt", "clone", "--select", "dbt_orders"),
            expected_returncode=1,
            expected_stdout_fragments=(
                "dbt_orders",
                "WARN",
                "warning_missing_source",
                "missing in origin environment",
            ),
        )
    ],
    ids=["dbt clone warns when origin warehouse relation is missing"],
)
def test_given_origin_relation_missing_when_cloning_then_warns(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name="clone_missing_origin_workspace",
    )
    drop_dbt_clone_origin_orders_relation(workspace=workspace)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout


@pytest.mark.parametrize(
    "test_case",
    CLONE_ERROR_E2E_TEST_CASES,
    ids=[case.description for case in CLONE_ERROR_E2E_TEST_CASES],
)
def test_given_invalid_clone_request_when_running_then_renders_clear_error(
    tmp_path: Path,
    test_case: DbtCloneE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = prepare_dbt_diff_workspace(
        tmp_path=tmp_path,
        workspace_name=test_case.description.replace(" ", "_"),
        include_production_ref=test_case.include_production_ref,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=workspace / "sqlbuild_project",
    )

    assert result.returncode == test_case.expected_returncode, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_stderr_fragments:
        assert fragment in result.stderr
