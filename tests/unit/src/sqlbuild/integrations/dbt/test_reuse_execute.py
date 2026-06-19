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
    execute_dbt_seeded_reuse_plan,
)
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtFreshSchemaReuseExecuteTestCase,
    DbtReuseExecuteTestCase,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_fresh_schema_reuse_execute_manifest,
    build_fresh_schema_reuse_execute_plan,
    build_reuse_execute_manifest,
    build_reuse_execute_plan,
    build_seeded_reuse_execute_plan,
)

SEEDED_REUSE_SKIP_TEST_CASES: tuple[DbtReuseExecuteTestCase, ...] = (
    DbtReuseExecuteTestCase(
        description="quietly skips when active destination cursor is ahead of origin",
        create_origin_relation=True,
        existing_destination_amount=902,
        expected_reused_unique_ids=(),
        expected_destination_rows=((3, 902),),
        expected_fingerprint_rows=(),
        cursor_column="event_time",
        destination_event_time="2026-01-03",
        destination_order_id=3,
    ),
    DbtReuseExecuteTestCase(
        description="quietly skips existing destination when cursor metadata is missing",
        create_origin_relation=True,
        existing_destination_amount=900,
        expected_reused_unique_ids=(),
        expected_destination_rows=((1, 900),),
        expected_fingerprint_rows=(),
        cursor_column=None,
        destination_event_time="2026-01-01",
        destination_order_id=1,
    ),
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
                "execution_mode": "reuse",
                "materialization": "table",
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


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="seeds missing destination from origin relation",
            create_origin_relation=True,
            existing_destination_amount=None,
            expected_reused_unique_ids=("model.analytics.fact_orders",),
            expected_destination_rows=((1, 900), (2, 901)),
            expected_fingerprint_rows=(),
        )
    ],
    ids=["seeds missing destination from origin relation"],
)
def test_given_seeded_reuse_missing_destination_when_executing_then_copies_origin_relation(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "seeded_reuse_execute.duckdb")})
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time "
            "UNION ALL "
            "SELECT 2 AS order_id, 901 AS amount, TIMESTAMP '2026-01-02' AS event_time",
        )

        seeded_unique_ids: tuple[str, ...] = execute_dbt_seeded_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_seeded_reuse_execute_plan(cursor_column="event_time"),
        )

        assert seeded_unique_ids == test_case.expected_reused_unique_ids
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
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="appends origin rows after active destination cursor",
            create_origin_relation=True,
            existing_destination_amount=900,
            expected_reused_unique_ids=("model.analytics.fact_orders",),
            expected_destination_rows=((1, 900), (2, 901)),
            expected_fingerprint_rows=(),
        )
    ],
    ids=["appends origin rows after active destination cursor"],
)
def test_given_seeded_reuse_destination_behind_when_executing_then_appends_origin_delta(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "seeded_reuse_execute.duckdb")})
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time "
            "UNION ALL "
            "SELECT 2 AS order_id, 901 AS amount, TIMESTAMP '2026-01-02' AS event_time",
        )
        adapter.execute(
            connection,
            "CREATE TABLE main.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time",
        )

        seeded_unique_ids: tuple[str, ...] = execute_dbt_seeded_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_seeded_reuse_execute_plan(cursor_column="event_time"),
        )

        assert seeded_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="appends full origin relation when destination cursor is null",
            create_origin_relation=True,
            existing_destination_amount=None,
            expected_reused_unique_ids=("model.analytics.fact_orders",),
            expected_destination_rows=((1, 900), (2, 901), (99, 0)),
            expected_fingerprint_rows=(),
        )
    ],
    ids=["appends full origin relation when destination cursor is null"],
)
def test_given_seeded_reuse_empty_destination_when_executing_then_appends_full_origin(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "seeded_reuse_execute.duckdb")})
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time "
            "UNION ALL "
            "SELECT 2 AS order_id, 901 AS amount, TIMESTAMP '2026-01-02' AS event_time",
        )
        adapter.execute(
            connection,
            "CREATE TABLE main.fact_orders AS "
            "SELECT 99 AS order_id, 0 AS amount, CAST(NULL AS TIMESTAMP) AS event_time",
        )

        seeded_unique_ids: tuple[str, ...] = execute_dbt_seeded_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_seeded_reuse_execute_plan(cursor_column="event_time"),
        )

        assert seeded_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="quietly skips when origin cursor is null",
            create_origin_relation=True,
            existing_destination_amount=900,
            expected_reused_unique_ids=(),
            expected_destination_rows=((1, 900),),
            expected_fingerprint_rows=(),
        )
    ],
    ids=["quietly skips when origin cursor is null"],
)
def test_given_seeded_reuse_origin_cursor_missing_when_executing_then_preserves_destination(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "seeded_reuse_execute.duckdb")})
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS "
            "SELECT 2 AS order_id, 901 AS amount, CAST(NULL AS TIMESTAMP) AS event_time",
        )
        adapter.execute(
            connection,
            "CREATE TABLE main.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time",
        )

        seeded_unique_ids: tuple[str, ...] = execute_dbt_seeded_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_seeded_reuse_execute_plan(cursor_column="event_time"),
        )

        assert seeded_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtReuseExecuteTestCase(
            description="appends integer cursor delta",
            create_origin_relation=True,
            existing_destination_amount=900,
            expected_reused_unique_ids=("model.analytics.fact_orders",),
            expected_destination_rows=((1, 900), (2, 901)),
            expected_fingerprint_rows=(),
        )
    ],
    ids=["appends integer cursor delta"],
)
def test_given_seeded_reuse_integer_cursor_when_executing_then_appends_origin_delta(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "seeded_reuse_execute.duckdb")})
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, 10 AS event_index "
            "UNION ALL SELECT 2 AS order_id, 901 AS amount, 11 AS event_index",
        )
        adapter.execute(
            connection,
            "CREATE TABLE main.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, 10 AS event_index",
        )

        seeded_unique_ids: tuple[str, ...] = execute_dbt_seeded_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_seeded_reuse_execute_plan(cursor_column="event_index"),
        )

        assert seeded_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    SEEDED_REUSE_SKIP_TEST_CASES,
    ids=[case.description for case in SEEDED_REUSE_SKIP_TEST_CASES],
)
def test_given_seeded_reuse_skip_condition_when_executing_then_preserves_destination(
    tmp_path: Path,
    test_case: DbtReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "seeded_reuse_execute.duckdb")})
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS prod")
        adapter.execute(
            connection,
            "CREATE TABLE prod.fact_orders AS "
            "SELECT 1 AS order_id, 900 AS amount, TIMESTAMP '2026-01-01' AS event_time "
            "UNION ALL "
            "SELECT 2 AS order_id, 901 AS amount, TIMESTAMP '2026-01-02' AS event_time",
        )
        adapter.execute(
            connection,
            "CREATE TABLE main.fact_orders AS "
            f"SELECT {test_case.destination_order_id} AS order_id, "
            f"{test_case.existing_destination_amount} AS amount, "
            f"TIMESTAMP '{test_case.destination_event_time}' AS event_time",
        )

        seeded_unique_ids: tuple[str, ...] = execute_dbt_seeded_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_reuse_execute_manifest(),
            plan=build_seeded_reuse_execute_plan(cursor_column=test_case.cursor_column),
        )

        assert seeded_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM main.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
    finally:
        adapter.close(connection)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtFreshSchemaReuseExecuteTestCase(
            description="reuses into fresh dev schema and writes fingerprint into fresh schema",
            fingerprint_schema="dev_alice",
            expected_reused_unique_ids=("model.analytics.fact_orders",),
            expected_destination_rows=((1, 900),),
            expected_fingerprint_node_names=("model.analytics.fact_orders",),
        )
    ],
    ids=["reuses into fresh dev schema and writes fingerprint into fresh schema"],
)
def test_given_fresh_dev_schema_when_executing_complete_reuse_then_creates_schema_and_swaps(
    tmp_path: Path,
    test_case: DbtFreshSchemaReuseExecuteTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": str(tmp_path / "fresh_schema_reuse.duckdb")})
    warnings: list[str] = []
    try:
        adapter.execute(connection, "CREATE SCHEMA IF NOT EXISTS marts")
        adapter.execute(
            connection,
            "CREATE TABLE marts.fact_orders AS SELECT 1 AS order_id, 900 AS amount",
        )

        reused_unique_ids: tuple[str, ...] = execute_dbt_complete_reuse_plan(
            adapter=adapter,
            connection=connection,
            manifest=build_fresh_schema_reuse_execute_manifest(),
            plan=build_fresh_schema_reuse_execute_plan(),
            run_id="run-1",
            fingerprint_database=None,
            fingerprint_schema=test_case.fingerprint_schema,
            target_name="dev",
            warnings=warnings,
        )

        assert reused_unique_ids == test_case.expected_reused_unique_ids
        assert adapter.execute(
            connection,
            "SELECT order_id, amount FROM dev_marts.fact_orders ORDER BY order_id",
        ).fetchall() == list(test_case.expected_destination_rows)
        assert adapter.execute(
            connection,
            f"SELECT node_name FROM {test_case.fingerprint_schema}._sqlbuild_fingerprints "
            "ORDER BY node_name",
        ).fetchall() == [(name,) for name in test_case.expected_fingerprint_node_names]
        assert warnings == []
    finally:
        adapter.close(connection)
