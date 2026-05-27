from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import build_virtual_plan_repo_files
from tests.e2e.src.sqlbuild.cli.commands.main.reconcile._test_types import (
    ReconcileE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="report shows no issues for healthy vde",
            command=("reconcile", "--virtual-env", "dev"),
            expected_fragments=("Reconcile report for dev: no issues.",),
        )
    ],
    ids=["report shows no issues for healthy vde"],
)
def test_given_healthy_virtual_environment_when_reconciling_then_report_is_clean(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_report",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="repair-view recreates missing logical vde view",
            command=(
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "fact_orders",
            ),
            expected_fragments=("Repaired logical view for fact_orders in dev.",),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
        )
    ],
    ids=["repair-view recreates missing logical vde view"],
)
def test_given_missing_logical_view_when_repairing_then_it_is_recreated(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_repair_view",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql='DROP VIEW "dev__dev"."fact_orders"',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="attach rebinds logical ref to tracked physical relation",
            command=(),
            expected_fragments=("Attached fact_orders to",),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),),
        )
    ],
    ids=["attach rebinds logical ref to tracked physical relation"],
)
def test_given_tracked_physical_relation_when_attaching_then_logical_ref_is_rebound(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_attach",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"), project_dir=project_dir
        ).returncode
        == 0
    )
    attach_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name, version_hash "
            "FROM sqlbuild_state.physical_relations "
            "WHERE model_name = 'fact_orders' ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name, _version_hash = attach_relation_rows[0]
    attach_relation: str = f'"{schema_name}"."{relation_name}"'

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "reconcile",
            "attach",
            "--virtual-env",
            "dev",
            "--model",
            "fact_orders",
            "--physical-relation",
            attach_relation,
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    for query_sql, expected_rows in test_case.expected_query_results:
        assert query_duckdb(db_path=project_dir / "warehouse.duckdb", sql=query_sql) == list(
            expected_rows
        )
