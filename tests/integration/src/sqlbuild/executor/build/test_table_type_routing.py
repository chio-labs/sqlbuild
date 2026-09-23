"""Integration tests for per-model table-type conversion routing during real builds."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

import sqlbuild.compiler.planner.main.execution.execution as planner_execution_module
import sqlbuild.executor.build.classes.build_scheduler as build_scheduler_module
from tests.integration.src.sqlbuild.executor.build._test_types import TableTypeRoutingTestCase
from tests.integration.src.sqlbuild.executor.build.helpers import (
    build_project_json,
    drift_for_models,
    duckdb_row_count,
    failing_table_type_conversion,
    recording_table_type_conversion,
    write_build_project_files,
)

_PROJECT_FILES: dict[str, str] = {
    "sqlbuild_project.toml": (
        'name = "demo"\nadapter = "duckdb"\n\n[connection]\ndatabase = "demo.duckdb"\n'
    ),
    "models/customer_totals.sql": (
        "MODEL (materialized table);\n\n"
        "SELECT customer_id, SUM(amount) AS total FROM raw_orders GROUP BY customer_id"
    ),
    "models/orders.sql": (
        "MODEL (\n"
        "  materialized incremental,\n"
        "  incremental_strategy append,\n"
        "  cursor updated_at,\n"
        "  cursor_type timestamp,\n"
        "  cursor_grain second,\n"
        ");\n\n"
        "SELECT id, customer_id, amount, updated_at FROM raw_orders"
    ),
}
_SETUP_SQL: str = (
    "CREATE TABLE raw_orders AS SELECT * FROM (VALUES "
    "(1, 10, 5, TIMESTAMP '2024-01-01'), (2, 10, 7, TIMESTAMP '2024-01-02')) "
    "AS t(id, customer_id, amount, updated_at)"
)
_NEW_ORDER_SQL: str = "INSERT INTO raw_orders VALUES (3, 11, 4, TIMESTAMP '2024-01-03')"


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeRoutingTestCase(
            description="rebuilt table skips conversion and carried-over table converts first",
            conversion_error=None,
            expected_exit_code=0,
            expected_conversions=(("orders", 2),),
            expected_order_rows=5,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_table_type_drift_when_building_then_only_carried_over_tables_convert_before_build(
    test_case: TableTypeRoutingTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_build_project_files(project_dir=tmp_path, project_files=_PROJECT_FILES)
    with duckdb.connect(str(tmp_path / "demo.duckdb")) as setup:
        setup.execute(_SETUP_SQL)
    initial_exit, _ = build_project_json(project_dir=tmp_path, capsys=capsys)
    with duckdb.connect(str(tmp_path / "demo.duckdb")) as setup:
        setup.execute(_NEW_ORDER_SQL)
    conversions: list[tuple[str, int]] = []
    monkeypatch.setattr(
        planner_execution_module,
        "plan_table_types",
        drift_for_models(model_names=("customer_totals", "orders")),
    )
    monkeypatch.setattr(
        build_scheduler_module,
        "apply_table_type_conversion",
        recording_table_type_conversion(conversions=conversions),
    )

    exit_code, _ = build_project_json(project_dir=tmp_path, capsys=capsys)

    assert initial_exit == 0
    assert exit_code == test_case.expected_exit_code
    assert tuple(conversions) == test_case.expected_conversions
    assert (
        duckdb_row_count(database=tmp_path / "demo.duckdb", table="orders")
        == test_case.expected_order_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        TableTypeRoutingTestCase(
            description="failed conversion fails its model before any data change",
            conversion_error="conversion copy was not created with the desired type",
            expected_exit_code=1,
            expected_conversions=(("orders", 2),),
            expected_order_rows=2,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_failing_table_type_conversion_when_building_then_model_fails_without_dml(
    test_case: TableTypeRoutingTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_build_project_files(project_dir=tmp_path, project_files=_PROJECT_FILES)
    with duckdb.connect(str(tmp_path / "demo.duckdb")) as setup:
        setup.execute(_SETUP_SQL)
    initial_exit, _ = build_project_json(project_dir=tmp_path, capsys=capsys)
    with duckdb.connect(str(tmp_path / "demo.duckdb")) as setup:
        setup.execute(_NEW_ORDER_SQL)
    conversions: list[tuple[str, int]] = []
    monkeypatch.setattr(
        planner_execution_module,
        "plan_table_types",
        drift_for_models(model_names=("customer_totals", "orders")),
    )
    monkeypatch.setattr(
        build_scheduler_module,
        "apply_table_type_conversion",
        failing_table_type_conversion(
            conversions=conversions, error=str(test_case.conversion_error)
        ),
    )

    exit_code, payload = build_project_json(project_dir=tmp_path, capsys=capsys)
    serialized: str = json.dumps(payload)
    statuses: dict[str, str] = {item["name"]: item["status"] for item in payload["assets"]}

    assert initial_exit == 0
    assert exit_code == test_case.expected_exit_code
    assert tuple(conversions) == test_case.expected_conversions
    assert str(test_case.conversion_error) in serialized
    assert statuses == {"customer_totals": "success", "orders": "failed"}
    assert (
        duckdb_row_count(database=tmp_path / "demo.duckdb", table="orders")
        == test_case.expected_order_rows
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
