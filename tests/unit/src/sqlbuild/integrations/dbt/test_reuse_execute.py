from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest
from duckdb import CatalogException

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.integrations.dbt.pipeline.helpers.reuse_execute import (
    execute_dbt_complete_reuse_plan,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtReuseExecuteTestCase
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_reuse_execute_manifest,
    build_reuse_execute_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="copies prod table into dev and writes dbt fingerprint",
            create_origin_relation=True,
            existing_destination_amount=None,
            expected_reused_unique_ids=("model.analytics.fact_orders",),
            expected_destination_rows=((1, 900),),
            expected_fingerprint_rows=(
                ("dbt", "model.analytics.fact_orders", "main", "fact_orders"),
            ),
            expected_metadata={
                "dbt_target_name": "dev",
                "destination_relation": "main.fact_orders",
                "materialization": "table",
                "materialization_mode": "reuse_clone",
                "origin_relation": "prod.fact_orders",
                "reuse_mode": "complete",
                "status": "success",
            },
        )
    ],
    ids=["copies prod table into dev and writes dbt fingerprint"],
)
def test_given_complete_reuse_plan_when_executing_then_copies_table_and_writes_fingerprint(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "reuse_execute.duckdb")})
    warnings: list[str] = []
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS SELECT 1 AS order_id, 900 AS amount",
        )

        reused_unique_ids: tuple[str, ...] = execute_dbt_complete_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_reuse_execute_plan(),
            run_id="run-1",
            fingerprint_database=None,
            fingerprint_schema="main",
            target_name="dev",
            warnings=warnings,
        )

        assert reused_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
        assert adapter.execute(
            connection,
            "SELECT node_type, node_name, target_schema, target_name "
            "FROM main._sqlbuild_fingerprints ORDER BY node_name",
        ).fetchall() == list(test_case.expected_fingerprint_rows)
        metadata_row: tuple[str] = adapter.execute(
            connection,
            "SELECT metadata_json_b64 FROM main._sqlbuild_fingerprints ORDER BY node_name",
        ).fetchone()
        decoded_metadata: object = json.loads(base64.b64decode(metadata_row[0]).decode("utf-8"))
        assert decoded_metadata == test_case.expected_metadata
        assert warnings == []
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="preserves existing dev table when staging copy fails",
            create_origin_relation=False,
            existing_destination_amount=5,
            expected_reused_unique_ids=(),
            expected_destination_rows=((1, 5),),
            expected_fingerprint_rows=(),
            expected_error=True,
        )
    ],
    ids=["preserves existing dev table when staging copy fails"],
)
def test_given_complete_reuse_copy_failure_when_executing_then_preserves_existing_destination(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "reuse_execute.duckdb")})
    warnings: list[str] = []
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE main.fact_orders AS "
            f"SELECT 1 AS order_id, {test_case.existing_destination_amount} AS amount",
        )

        with pytest.raises(CatalogException):
            execute_dbt_complete_reuse_plan(
                adapter=adapter,
                connection=connection,
                manifest=build_reuse_execute_manifest(),
                plan=build_reuse_execute_plan(),
                run_id="run-1",
                fingerprint_database=None,
                fingerprint_schema="main",
                target_name="dev",
                warnings=warnings,
            )

        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
        assert not adapter.relation_exists(
            connection,
            database=None,
            schema="main",
            name="_sqlbuild_fingerprints",
        )
        assert warnings == []
    finally:
        adapter.close(connection)
