"""E2E tests for sqb run command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.run._test_types import RunE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    prepare_waffle_shop,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RunE2ETestCase(
            description="run materializes tables and views with correct data",
            expected_exit_code=0,
            expected_table_names=("daily_revenue", "dim_customers", "fact_orders"),
            expected_view_names=("stg_customers", "stg_orders", "stg_payments"),
            expected_fact_orders_data=(
                (1, 1, "Classic Belgian", "completed"),
                (2, 1, "Cheddar Herb", "completed"),
                (3, 2, "Chicken and Waffle", "completed"),
                (4, 3, "Liege", "completed"),
                (5, 4, "Classic Belgian", "completed"),
                (6, 4, "Brussels", "completed"),
                (7, 5, "Everything Bagel", "cancelled"),
                (8, 1, "Liege", "completed"),
                (9, 2, "Chicken and Waffle", "preparing"),
                (10, 3, "Classic Belgian", "placed"),
            ),
        ),
    ],
    ids=["run materializes tables and views with correct data"],
)
def test_given_waffle_shop_project_when_running_run_then_warehouse_state_matches_expected(
    test_case: RunE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_waffle_shop(tmp_path)
    db_path: Path = project_dir / "waffle_shop.duckdb"

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "run"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    run_sql_path: Path = project_dir / "target" / "run" / "models" / "marts" / "fact_orders.sql"
    assert run_sql_path.exists()
    run_sql: str = run_sql_path.read_text(encoding="utf-8")
    assert "CREATE OR REPLACE TABLE main.fact_orders__staging AS" in run_sql
    assert "ALTER TABLE main.fact_orders__staging RENAME TO fact_orders;" in run_sql

    table_name: str
    for table_name in test_case.expected_table_names:
        assert table_exists(db_path=db_path, table_name=table_name), (
            f"table {table_name} should exist"
        )

    view_name: str
    for view_name in test_case.expected_view_names:
        assert table_exists(db_path=db_path, table_name=view_name), f"view {view_name} should exist"

    fact_sql: str = (
        "SELECT order_id, customer_id, waffle_name, order_status "
        "FROM main.fact_orders ORDER BY order_id"
    )
    fact_rows: list[tuple[Any, ...]] = query_duckdb(db_path=db_path, sql=fact_sql)
    assert tuple(tuple(r) for r in fact_rows) == test_case.expected_fact_orders_data
