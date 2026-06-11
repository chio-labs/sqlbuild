from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.plan.helpers import build_virtual_plan_repo_files
from tests.e2e.src.sqlbuild.cli.commands.main.reconcile._test_types import (
    ReconcileE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.reconcile.helpers import (
    build_virtual_seed_reconcile_repo_files,
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
            description="report detects missing logical seed view",
            command=("reconcile", "--virtual-env", "dev"),
            expected_fragments=(
                "Reconcile report for dev:",
                "missing logical seed target: order_amounts",
            ),
        )
    ],
    ids=["report detects missing logical seed view"],
)
def test_given_missing_logical_seed_view_when_reconciling_then_report_flags_seed_issue(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_seed_report",
        repo_files=build_virtual_seed_reconcile_repo_files(),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql='DROP VIEW "dev__dev"."order_amounts"',
    )

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
            description="repair-view recreates missing logical seed view",
            command=(
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--seed",
                "order_amounts",
            ),
            expected_fragments=(
                "Repair",
                "seed    order_amounts",
                "VDE     dev",
                "action  recreate logical seed view from state",
                "result  repaired",
            ),
            expected_query_results=(
                ("SELECT id, amount_cents FROM dev__dev.order_amounts ORDER BY id", ((1, 100),)),
            ),
        )
    ],
    ids=["repair-view recreates missing logical seed view"],
)
def test_given_missing_logical_seed_view_when_repairing_then_it_is_recreated(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_seed_repair",
        repo_files=build_virtual_seed_reconcile_repo_files(),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql='DROP VIEW "dev__dev"."order_amounts"',
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
            description="report detects missing physical seed relation",
            command=("reconcile", "--virtual-env", "dev"),
            expected_fragments=(
                "Reconcile report for dev:",
                "missing physical seed relation: order_amounts",
            ),
        )
    ],
    ids=["report detects missing physical seed relation"],
)
def test_given_missing_physical_seed_relation_when_reconciling_then_report_flags_seed_issue(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_seed_physical_report",
        repo_files=build_virtual_seed_reconcile_repo_files(),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts' "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name = physical_rows[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{schema_name}"."{relation_name}"',
    )

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
            description="report detects missing tracked physical seed state",
            command=("reconcile", "--virtual-env", "dev"),
            expected_fragments=(
                "Reconcile report for dev:",
                "missing tracked physical seed relation: order_amounts",
            ),
        )
    ],
    ids=["report detects missing tracked physical seed state"],
)
def test_given_missing_seed_physical_state_when_reconciling_then_report_flags_seed_issue(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_seed_physical_state_report",
        repo_files=build_virtual_seed_reconcile_repo_files(),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "DELETE FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'seed' AND artifact_name = 'order_amounts'"
        ),
    )

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
            description="report detects and repair-view recreates missing logical vde view",
            command=(
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "fact_orders",
            ),
            expected_fragments=(
                "Repair",
                "model   fact_orders",
                "VDE     dev",
                "action  recreate logical view from state",
                "result  repaired",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((1,),)),),
            expected_report_fragments=(
                "Virtual reconcile",
                "Reconcile report for dev:",
                "missing logical target: fact_orders",
            ),
        )
    ],
    ids=["report detects and repair-view recreates missing logical vde view"],
)
def test_given_missing_logical_view_when_reconciling_and_repairing_then_it_is_recreated(
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

    report_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("reconcile", "--virtual-env", "dev"),
        project_dir=project_dir,
    )

    assert report_result.returncode == 0, report_result.stdout + report_result.stderr
    for fragment in test_case.expected_report_fragments:
        assert fragment in report_result.stdout + report_result.stderr

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
            description="report detects and repair-view blocks missing physical relation",
            command=(
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "fact_orders",
            ),
            expected_exit_code=1,
            expected_fragments=("error[C252]: missing physical relation for 'fact_orders'",),
            expected_report_fragments=(
                "Virtual reconcile",
                "Reconcile report for dev:",
                "missing physical relation: fact_orders",
            ),
            unexpected_fragments=("Traceback",),
        )
    ],
    ids=["report detects and repair-view blocks missing physical relation"],
)
def test_given_missing_physical_relation_when_reconciling_and_repairing_then_it_blocks(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_missing_physical",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    physical_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name = physical_rows[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=f'DROP TABLE "{schema_name}"."{relation_name}"',
    )

    report_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("reconcile", "--virtual-env", "dev"),
        project_dir=project_dir,
    )

    assert report_result.returncode == 0, report_result.stdout + report_result.stderr
    for fragment in test_case.expected_report_fragments:
        assert fragment in report_result.stdout + report_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    combined_output: str = result.stdout + result.stderr
    assert result.returncode == test_case.expected_exit_code, combined_output
    for fragment in test_case.expected_fragments:
        assert fragment in combined_output
    for fragment in test_case.unexpected_fragments:
        assert fragment not in combined_output


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="attach rebinds logical ref to tracked physical relation",
            command=(),
            expected_fragments=(
                "Attach",
                "model     fact_orders",
                "VDE       dev",
                "physical",
                "result    attached",
            ),
            expected_query_results=(("SELECT id FROM dev__dev.fact_orders ORDER BY id", ((2,),)),),
            input_text="attach fact_orders\n",
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
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY updated_at DESC LIMIT 1"
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
        input_text=test_case.input_text,
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
            description="attach blocks untracked physical relation",
            command=(),
            expected_exit_code=1,
            expected_fragments=("is not a tracked relation",),
        )
    ],
    ids=["attach blocks untracked physical relation"],
)
def test_given_untracked_physical_relation_when_attaching_then_it_blocks(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_attach_untracked",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql='CREATE TABLE "dev__sqb_physical"."untracked_orders" AS SELECT 9 AS id',
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "reconcile",
            "attach",
            "--auto-approve",
            "--virtual-env",
            "dev",
            "--model",
            "fact_orders",
            "--physical-relation",
            '"dev__sqb_physical"."untracked_orders"',
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="attach blocks physical relation tracked for another model",
            command=(),
            expected_exit_code=1,
            expected_fragments=("is not a tracked relation for 'fact_orders'",),
        )
    ],
    ids=["attach blocks physical relation tracked for another model"],
)
def test_given_wrong_model_physical_relation_when_attaching_then_it_blocks_before_ref_update(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_attach_wrong_model",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    original_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
            "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
        ),
    )
    (project_dir / "models" / "dim_customers.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS customer_id\n",
        encoding="utf-8",
    )
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    wrong_model_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'dim_customers' "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name = wrong_model_relation_rows[0]

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "reconcile",
            "attach",
            "--auto-approve",
            "--virtual-env",
            "dev",
            "--model",
            "fact_orders",
            "--physical-relation",
            f'"{schema_name}"."{relation_name}"',
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    assert (
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
            ),
        )
        == original_ref_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="attach cancellation blocks before ref mutation",
            command=(),
            expected_exit_code=1,
            expected_fragments=("reconcile attach cancelled",),
            input_text="nope\n",
        )
    ],
    ids=["attach cancellation blocks before ref mutation"],
)
def test_given_wrong_confirmation_when_attaching_then_it_cancels(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_attach_cancelled",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    original_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
            "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
        ),
    )
    attach_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name = attach_relation_rows[0]

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "reconcile",
            "attach",
            "--virtual-env",
            "dev",
            "--model",
            "fact_orders",
            "--physical-relation",
            f'"{schema_name}"."{relation_name}"',
        ),
        project_dir=project_dir,
        input_text=test_case.input_text,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    assert (
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
            ),
        )
        == original_ref_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="repair-view blocks logical target table",
            command=(
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "fact_orders",
            ),
            expected_exit_code=1,
            expected_fragments=("logical target for 'fact_orders' is a table",),
        )
    ],
    ids=["repair-view blocks logical target table"],
)
def test_given_logical_target_table_when_repairing_view_then_it_blocks(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_repair_table_block",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            'DROP VIEW "dev__dev"."fact_orders"; '
            'CREATE TABLE "dev__dev"."fact_orders" AS SELECT 1 AS id'
        ),
    )

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
            description="attach blocks logical target table before ref mutation",
            command=(),
            expected_exit_code=1,
            expected_fragments=("logical target for 'fact_orders' is a table",),
        )
    ],
    ids=["attach blocks logical target table before ref mutation"],
)
def test_given_logical_target_table_when_attaching_then_it_blocks_before_ref_update(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_attach_table_block",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    original_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
            "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
        ),
    )
    (project_dir / "models" / "stg_orders.sql").write_text(
        "MODEL ();\n\nSELECT 2 AS id\n",
        encoding="utf-8",
    )
    assert (
        run_sqb(
            command=("--no-color", "build", "--virtual-env", "pr"),
            project_dir=project_dir,
        ).returncode
        == 0
    )
    attach_relation_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name = attach_relation_rows[0]
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql=(
            'DROP VIEW "dev__dev"."fact_orders"; '
            'CREATE TABLE "dev__dev"."fact_orders" AS SELECT 1 AS id'
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "reconcile",
            "attach",
            "--auto-approve",
            "--virtual-env",
            "dev",
            "--model",
            "fact_orders",
            "--physical-relation",
            f'"{schema_name}"."{relation_name}"',
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    assert (
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
            ),
        )
        == original_ref_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="repair-view blocks when target vde is locked",
            command=(
                "reconcile",
                "repair-view",
                "--virtual-env",
                "dev",
                "--model",
                "fact_orders",
            ),
            expected_exit_code=1,
            expected_fragments=("virtual environment 'dev' is locked",),
        )
    ],
    ids=["repair-view blocks when target vde is locked"],
)
def test_given_target_virtual_environment_lock_when_repairing_view_then_it_blocks(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_repair_locked",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    execute_duckdb(
        db_path=project_dir / "warehouse.duckdb",
        sql='DROP VIEW "dev__dev"."fact_orders"',
    )
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) "
            "VALUES ('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    assert (
        query_duckdb(
            db_path=project_dir / "warehouse.duckdb",
            sql=(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'dev__dev' AND table_name = 'fact_orders'"
            ),
        )
        == []
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ReconcileE2ETestCase(
            description="attach blocks when target vde is locked",
            command=(),
            expected_exit_code=1,
            expected_fragments=("virtual environment 'dev' is locked",),
        )
    ],
    ids=["attach blocks when target vde is locked"],
)
def test_given_target_virtual_environment_lock_when_attaching_then_it_blocks_before_ref_update(
    test_case: ReconcileE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="virtual_reconcile_attach_locked",
        repo_files=build_virtual_plan_repo_files(stg_orders_sql="SELECT 1 AS id"),
    )
    assert run_sqb(command=("state", "init"), project_dir=project_dir).returncode == 0
    assert run_sqb(command=("--no-color", "build"), project_dir=project_dir).returncode == 0
    original_ref_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
            "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
        ),
    )
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
            "SELECT schema_name, relation_name FROM sqlbuild_state.physical_relations "
            "WHERE artifact_type = 'model' AND artifact_name = 'fact_orders' "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
    )
    schema_name, relation_name = attach_relation_rows[0]
    execute_duckdb(
        db_path=project_dir / "state.duckdb",
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) "
            "VALUES ('virtual_env:dev', 'test-owner', TIMESTAMP '2999-01-01', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "reconcile",
            "attach",
            "--auto-approve",
            "--virtual-env",
            "dev",
            "--model",
            "fact_orders",
            "--physical-relation",
            f'"{schema_name}"."{relation_name}"',
        ),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout + result.stderr
    assert (
        query_duckdb(
            db_path=project_dir / "state.duckdb",
            sql=(
                "SELECT version_hash FROM sqlbuild_state.virtual_environment_model_refs "
                "WHERE virtual_environment_name = 'dev' AND model_name = 'fact_orders'"
            ),
        )
        == original_ref_rows
    )
