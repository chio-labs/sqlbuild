"""Snapshot scenarios shared by every real warehouse."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.warehouses._test_types import (
    SnapshotApplyTestCase,
    SnapshotTestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.warehouses.harness import (
    Rows,
    WarehouseHarness,
    WarehouseSetup,
    on_warehouses,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    build_current_check_customers_model_sql,
    build_current_customers_model_sql,
    build_current_delete_customers_model_sql,
    build_historical_check_daily_model_sql,
    build_historical_timestamp_extracts_model_sql,
    build_real_warehouse_existing_snapshot_project_files,
    build_real_warehouse_snapshot_project_files,
    prepare_inline_project,
    run_sqb,
    stringify_warehouse_rows,
)

_SELECTED_SNAPSHOT_BUILD: tuple[str, ...] = (
    "--no-color",
    "build",
    "--concurrency",
    "4",
    "--select",
    "+current_customer_snapshot",
)


def _history_rows(
    warehouse: WarehouseHarness, schema_name: str, name: str, column: str, start: str, end: str
) -> Rows:
    return stringify_warehouse_rows(
        warehouse.fetch_rows(
            schema_name,
            warehouse.adapt_sql(
                f"SELECT customer_id, {column}, {warehouse.date_sql(start)}, "
                f"{warehouse.date_sql(end)} FROM {warehouse.relation(schema_name, name)} "
                f"ORDER BY customer_id, {start}"
            ),
        )
    )


def _current_customer_rows(warehouse: WarehouseHarness, schema_name: str) -> Rows:
    relation: str = warehouse.relation(schema_name, "current_customer_snapshot")
    return stringify_warehouse_rows(
        warehouse.fetch_rows(
            schema_name,
            warehouse.adapt_sql(
                "SELECT customer_id, region_id, plan, "
                f"{warehouse.date_sql('effective_from')}, {warehouse.date_sql('effective_to')} "
                f"FROM {relation} ORDER BY customer_id, region_id, effective_from"
            ),
        )
    )


def _open_version_rows(
    warehouse: WarehouseHarness, schema_name: str, name: str, column: str
) -> Rows:
    flag: str = warehouse.null_flag_sql("valid_to")
    return stringify_warehouse_rows(
        warehouse.fetch_rows(
            schema_name,
            warehouse.adapt_sql(
                f"SELECT customer_id, {column}, {flag} FROM {warehouse.relation(schema_name, name)} "
                f"ORDER BY customer_id, {column}, {flag}"
            ),
        )
    )


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses(
        WarehouseSetup("bigquery", precreate_schema=False),
        "snowflake",
        "databricks",
        "postgres",
        "sqlserver",
        "clickhouse",
    ),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotTestCase(
            description="executes snapshot scd2 matrix",
            expected_current_rows_after_initial_build=(("1", "10", "basic", "2026-01-01", None),),
            expected_current_rows_after_recovery=(
                ("1", "10", "basic", "2026-01-01", "2026-01-02"),
                ("1", "10", "pro", "2026-01-02", None),
            ),
            expected_historical_timestamp_rows=(
                ("1", "basic", "2026-01-01", "2026-01-03"),
                ("1", "pro", "2026-01-03", None),
                ("2", "trial", "2026-01-02", None),
            ),
            expected_historical_check_rows=(
                ("1", "active", "2026-01-01", "2026-01-03"),
                ("1", "paused", "2026-01-03", None),
                ("2", "active", "2026-01-01", "2026-01-02"),
                ("2", "active", "2026-01-03", None),
            ),
            expected_failure_fragments=(
                "current_customer_snapshot",
                "delta audit for 'current_customer_snapshot' failed before target update",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_project_when_building_then_scd2_history_is_valid(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: SnapshotTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_snapshot")
    project_name: str = f"{warehouse.name}_snapshot_project"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            path: warehouse.adapt_sql(contents)
            for path, contents in build_real_warehouse_snapshot_project_files(
                project_toml=warehouse.project_toml(project_name, schema_name)
            ).items()
        },
    )
    warehouse.precreate(schema_name)
    customers_model: Path = project_dir / "models" / "current_customers.sql"

    try:
        with warehouse.timing("snapshot initial build"):
            initial_result: subprocess.CompletedProcess[str] = run_sqb(
                command=("--no-color", "build", "--concurrency", "4"), project_dir=project_dir
            )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
        assert (
            _current_customer_rows(warehouse, schema_name)
            == test_case.expected_current_rows_after_initial_build
        )
        assert (
            _history_rows(
                warehouse,
                schema_name,
                "historical_customer_snapshot",
                "plan",
                "valid_from",
                "valid_to",
            )
            == test_case.expected_historical_timestamp_rows
        )
        assert (
            _history_rows(
                warehouse,
                schema_name,
                "historical_membership_snapshot",
                "status",
                "valid_from",
                "valid_to",
            )
            == test_case.expected_historical_check_rows
        )

        customers_model.write_text(
            warehouse.adapt_sql(
                build_current_customers_model_sql(plan="blocked", updated_at="2026-01-02 00:00:00")
            ),
            encoding="utf-8",
        )
        with warehouse.timing("snapshot delta audit failure build"):
            failure_result: subprocess.CompletedProcess[str] = run_sqb(
                command=_SELECTED_SNAPSHOT_BUILD, project_dir=project_dir
            )
        assert failure_result.returncode == 1, failure_result.stdout + failure_result.stderr
        for fragment in test_case.expected_failure_fragments:
            assert fragment in failure_result.stdout + failure_result.stderr
        run_payloads: tuple[dict[str, Any], ...] = tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in (project_dir / "target" / "executions").glob("*/run.json")
        )
        assert any(payload["build_status"] == "failed" for payload in run_payloads)
        assert (
            _current_customer_rows(warehouse, schema_name)
            == test_case.expected_current_rows_after_initial_build
        )

        customers_model.write_text(
            warehouse.adapt_sql(
                build_current_customers_model_sql(plan="pro", updated_at="2026-01-02 00:00:00")
            ),
            encoding="utf-8",
        )
        with warehouse.timing("snapshot recovery build"):
            recovery_result: subprocess.CompletedProcess[str] = run_sqb(
                command=_SELECTED_SNAPSHOT_BUILD, project_dir=project_dir
            )
        assert recovery_result.returncode == 0, recovery_result.stdout + recovery_result.stderr
        assert (
            _current_customer_rows(warehouse, schema_name)
            == test_case.expected_current_rows_after_recovery
        )
    finally:
        warehouse.cleanup_schema(schema_name)


@pytest.mark.parametrize(
    "warehouse",
    on_warehouses(
        WarehouseSetup("bigquery", precreate_schema=False),
        "snowflake",
        "databricks",
        "postgres",
        "sqlserver",
        "clickhouse",
    ),
    indirect=True,
)
@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotApplyTestCase(
            description="applies existing-target snapshot changes",
            expected_current_check_rows=(
                ("1", "active", False),
                ("1", "paused", True),
                ("2", "active", True),
            ),
            expected_current_delete_rows=(
                ("1", "basic", False),
                ("1", "pro", True),
                ("2", "trial", False),
            ),
            expected_historical_timestamp_rows=(
                ("1", "basic", "2026-01-01", "2026-01-03"),
                ("1", "pro", "2026-01-03", None),
                ("2", "trial", "2026-01-01", "2026-01-04"),
            ),
            expected_historical_check_rows=(
                ("1", "active", "2026-01-01", "2026-01-03"),
                ("1", "paused", "2026-01-03", None),
                ("2", "active", "2026-01-01", "2026-01-02"),
                ("2", "active", "2026-01-03", None),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_existing_snapshot_targets_when_building_then_apply_sql_succeeds(
    tmp_path: Path,
    warehouse: WarehouseHarness,
    test_case: SnapshotApplyTestCase,
) -> None:
    schema_name: str = warehouse.unique_schema("sqlbuild_snapshot_apply")
    project_name: str = f"{warehouse.name}_snapshot_apply_project"
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name=project_name,
        repo_files={
            path: warehouse.adapt_sql(contents)
            for path, contents in build_real_warehouse_existing_snapshot_project_files(
                project_toml=warehouse.project_toml(project_name, schema_name)
            ).items()
        },
    )
    warehouse.precreate(schema_name)
    models: Path = project_dir / "models"

    try:
        with warehouse.timing("snapshot apply initial build"):
            initial_result: subprocess.CompletedProcess[str] = run_sqb(
                command=("--no-color", "build", "--concurrency", "4"), project_dir=project_dir
            )
        assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr

        for name, sql in (
            ("current_check_customers", build_current_check_customers_model_sql(changed=True)),
            ("current_delete_customers", build_current_delete_customers_model_sql(changed=True)),
            (
                "historical_timestamp_extracts",
                build_historical_timestamp_extracts_model_sql(changed=True),
            ),
            ("historical_check_daily", build_historical_check_daily_model_sql(changed=True)),
        ):
            (models / f"{name}.sql").write_text(warehouse.adapt_sql(sql), encoding="utf-8")

        with warehouse.timing("snapshot apply update build"):
            apply_result: subprocess.CompletedProcess[str] = run_sqb(
                command=("--no-color", "build", "--concurrency", "4"), project_dir=project_dir
            )
        assert apply_result.returncode == 0, apply_result.stdout + apply_result.stderr
        assert _open_version_rows(
            warehouse, schema_name, "current_check_snapshot", "status"
        ) == tuple(
            (customer, status, warehouse.flag(is_open))
            for customer, status, is_open in test_case.expected_current_check_rows
        )
        assert _open_version_rows(
            warehouse, schema_name, "current_delete_snapshot", "plan"
        ) == tuple(
            (customer, plan, warehouse.flag(is_open))
            for customer, plan, is_open in test_case.expected_current_delete_rows
        )
        assert (
            _history_rows(
                warehouse,
                schema_name,
                "historical_timestamp_snapshot",
                "plan",
                "valid_from",
                "valid_to",
            )
            == test_case.expected_historical_timestamp_rows
        )
        assert (
            _history_rows(
                warehouse,
                schema_name,
                "historical_check_snapshot",
                "status",
                "valid_from",
                "valid_to",
            )
            == test_case.expected_historical_check_rows
        )
        assert warehouse.snapshot_leftovers(schema_name) == ()
    finally:
        warehouse.cleanup_schema(schema_name)
