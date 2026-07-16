"""Integration tests for DuckDB snapshot adapter SQL methods."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.models import SnapshotChangeTarget
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from tests.integration.src.sqlbuild.adapters.duckdb._test_types import (
    SnapshotAdapterMethodsTestCase,
    SnapshotTransactionRollbackTestCase,
)
from tests.integration.src.sqlbuild.adapters.duckdb.helpers import (
    InsertFaultDuckDbAdapter,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotAdapterMethodsTestCase(
            description="duckdb snapshot adapter methods execute valid SQL for each snapshot shape",
            expected_initial_custom_rows=((1, "us", "basic", "2024-01-01 00:00:00", None),),
            expected_timestamp_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
                (2, "basic", "2024-01-02 00:00:00", None),
            ),
            expected_timestamp_hard_delete_rows=((1, "us", True), (1, "eu", False)),
            expected_check_rows=((1, "basic", False), (1, "pro", True), (2, "basic", True)),
            expected_historical_timestamp_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
                (2, "basic", "2024-01-02 00:00:00", None),
            ),
            expected_historical_changes_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
            ),
            expected_historical_check_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
                (2, "basic", "2024-01-02 00:00:00", None),
            ),
            expected_historical_check_apply_rows=(
                (1, "basic", "2024-01-01 00:00:00", "2024-01-03 00:00:00"),
                (1, "pro", "2024-01-03 00:00:00", None),
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_adapter_methods_when_executing_rendered_sql_then_updates_history(
    test_case: SnapshotAdapterMethodsTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> None:
    connection.execute(
        "CREATE TABLE main.initial_custom_source AS "
        "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
        "TIMESTAMP '2024-01-01' AS updated_at"
    )
    statement: str
    for statement in adapter.render_create_initial_snapshot_destination(
        destination="main.initial_custom_target",
        origin="main.initial_custom_source",
        snapshot_strategy="timestamp",
        updated_at_column="updated_at",
        observed_at_column=None,
        valid_from_column="effective_from",
        valid_to_column="effective_to",
        initial_valid_from=None,
    ):
        connection.execute(statement)
    initial_custom_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, region, plan, CAST(effective_from AS VARCHAR), "
            "CAST(effective_to AS VARCHAR) FROM main.initial_custom_target"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.ts_target AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS updated_at, "
        "TIMESTAMP '2024-01-01' AS valid_from, CAST(NULL AS TIMESTAMP) AS valid_to"
    )
    connection.execute(
        "CREATE TABLE main.ts_source AS "
        "SELECT 1 AS customer_id, 'pro' AS plan, TIMESTAMP '2024-01-03' AS updated_at "
        "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-02' AS updated_at"
    )
    for statement in adapter.render_apply_timestamp_snapshot_changes(
        destination="main.ts_target",
        origin="main.ts_source",
        unique_key=("customer_id",),
        updated_at_column="updated_at",
        observed_at_column=None,
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        initial_valid_from=None,
        output_columns=("customer_id", "plan", "updated_at"),
        invalidate_hard_deletes=False,
    ):
        connection.execute(statement)
    timestamp_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.ts_target ORDER BY customer_id, valid_from"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.ts_delete_target AS "
        "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
        "TIMESTAMP '2024-01-01' AS updated_at, TIMESTAMP '2024-01-01' AS valid_from, "
        "CAST(NULL AS TIMESTAMP) AS valid_to "
        "UNION ALL SELECT 1 AS customer_id, 'eu' AS region, 'basic' AS plan, "
        "TIMESTAMP '2024-01-01' AS updated_at, TIMESTAMP '2024-01-01' AS valid_from, "
        "CAST(NULL AS TIMESTAMP) AS valid_to"
    )
    connection.execute(
        "CREATE TABLE main.ts_delete_source AS "
        "SELECT 1 AS customer_id, 'us' AS region, 'basic' AS plan, "
        "TIMESTAMP '2024-01-01' AS updated_at"
    )
    for statement in adapter.render_apply_timestamp_snapshot_changes(
        destination="main.ts_delete_target",
        origin="main.ts_delete_source",
        unique_key=("customer_id", "region"),
        updated_at_column="updated_at",
        observed_at_column=None,
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        initial_valid_from=None,
        output_columns=("customer_id", "region", "plan", "updated_at"),
        invalidate_hard_deletes=True,
    ):
        connection.execute(statement)
    timestamp_hard_delete_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, region, valid_to IS NULL FROM main.ts_delete_target "
            "ORDER BY region DESC"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.check_target AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, 'active' AS status, "
        "TIMESTAMP '2024-01-01' AS valid_from, CAST(NULL AS TIMESTAMP) AS valid_to"
    )
    connection.execute(
        "CREATE TABLE main.check_source AS "
        "SELECT 1 AS customer_id, 'pro' AS plan, 'paused' AS status "
        "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, 'active' AS status"
    )
    for statement in adapter.render_apply_check_snapshot_changes(
        target=SnapshotChangeTarget(
            destination="main.check_target",
            origin="main.check_source",
            unique_key=("customer_id",),
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "status"),
        ),
        check_columns=("status",),
        updated_at_column=None,
        observed_at_column=None,
        initial_valid_from=None,
        invalidate_hard_deletes=False,
    ):
        connection.execute(statement)
    check_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, valid_to IS NULL FROM main.check_target "
            "ORDER BY customer_id, valid_to IS NULL, plan"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.hist_ts_source AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS updated_at, "
        "TIMESTAMP '2024-01-02' AS observed_at "
        "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, TIMESTAMP '2024-01-03' AS updated_at, "
        "TIMESTAMP '2024-01-04' AS observed_at "
        "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-02' AS updated_at, "
        "TIMESTAMP '2024-01-04' AS observed_at"
    )
    for statement in adapter.render_create_initial_historical_timestamp_snapshot_destination(
        destination="main.hist_ts_target",
        origin="main.hist_ts_source",
        unique_key=("customer_id",),
        updated_at_column="updated_at",
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "plan", "updated_at", "observed_at"),
        invalidate_hard_deletes=False,
    ):
        connection.execute(statement)
    historical_timestamp_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.hist_ts_target ORDER BY customer_id, valid_from"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.hist_changes_target AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS updated_at, "
        "TIMESTAMP '2024-01-01' AS valid_from, CAST(NULL AS TIMESTAMP) AS valid_to"
    )
    connection.execute(
        "CREATE TABLE main.hist_changes_source AS "
        "SELECT 1 AS customer_id, 'pro' AS plan, TIMESTAMP '2024-01-03' AS updated_at, "
        "TIMESTAMP '2024-01-10' AS observed_at"
    )
    for statement in adapter.render_apply_historical_timestamp_changes(
        destination="main.hist_changes_target",
        origin="main.hist_changes_source",
        unique_key=("customer_id",),
        updated_at_column="updated_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "plan", "updated_at"),
    ):
        connection.execute(statement)
    historical_changes_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.hist_changes_target ORDER BY customer_id, valid_from"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.hist_check_source AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS observed_at "
        "UNION ALL SELECT 1 AS customer_id, 'pro' AS plan, TIMESTAMP '2024-01-03' AS observed_at "
        "UNION ALL SELECT 2 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-02' AS observed_at"
    )
    for statement in adapter.render_create_initial_historical_check_snapshot_destination(
        destination="main.hist_check_target",
        origin="main.hist_check_source",
        unique_key=("customer_id",),
        check_columns=("plan",),
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "plan", "observed_at"),
        invalidate_hard_deletes=False,
    ):
        connection.execute(statement)
    historical_check_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.hist_check_target ORDER BY customer_id, valid_from"
        ).fetchall()
    )

    connection.execute(
        "CREATE TABLE main.hist_check_apply_target AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS observed_at, "
        "TIMESTAMP '2024-01-01' AS valid_from, CAST(NULL AS TIMESTAMP) AS valid_to"
    )
    connection.execute(
        "CREATE TABLE main.hist_check_apply_source AS "
        "SELECT 1 AS customer_id, 'pro' AS plan, TIMESTAMP '2024-01-03' AS observed_at"
    )
    for statement in adapter.render_apply_historical_check_snapshot_changes(
        destination="main.hist_check_apply_target",
        origin="main.hist_check_apply_source",
        unique_key=("customer_id",),
        check_columns=("plan",),
        observed_at_column="observed_at",
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        output_columns=("customer_id", "plan", "observed_at"),
        invalidate_hard_deletes=False,
    ):
        connection.execute(statement)
    historical_check_apply_rows: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.hist_check_apply_target ORDER BY customer_id, valid_from"
        ).fetchall()
    )

    assert initial_custom_rows == test_case.expected_initial_custom_rows
    assert timestamp_rows == test_case.expected_timestamp_rows
    assert timestamp_hard_delete_rows == test_case.expected_timestamp_hard_delete_rows
    assert check_rows == test_case.expected_check_rows
    assert historical_timestamp_rows == test_case.expected_historical_timestamp_rows
    assert historical_changes_rows == test_case.expected_historical_changes_rows
    assert historical_check_rows == test_case.expected_historical_check_rows
    assert historical_check_apply_rows == test_case.expected_historical_check_apply_rows


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotTransactionRollbackTestCase(
            description="snapshot transaction rolls back when insert fails after close",
            expected_error_fragment="injected snapshot insert failure",
            expected_rows_after_failure=((1, "basic", "2024-01-01 00:00:00", None),),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snapshot_insert_failure_when_transaction_rolls_back_then_history_is_unchanged(
    test_case: SnapshotTransactionRollbackTestCase,
    connection: Any,
) -> None:
    adapter: InsertFaultDuckDbAdapter = InsertFaultDuckDbAdapter(fault_target="main.tx_target")
    connection.execute(
        "CREATE TABLE main.tx_target AS "
        "SELECT 1 AS customer_id, 'basic' AS plan, TIMESTAMP '2024-01-01' AS updated_at, "
        "TIMESTAMP '2024-01-01' AS valid_from, CAST(NULL AS TIMESTAMP) AS valid_to"
    )
    connection.execute(
        "CREATE TABLE main.tx_source AS "
        "SELECT 1 AS customer_id, 'pro' AS plan, TIMESTAMP '2024-01-03' AS updated_at"
    )
    statements: tuple[str, ...] = adapter.render_apply_timestamp_snapshot_changes(
        destination="main.tx_target",
        origin="main.tx_source",
        unique_key=("customer_id",),
        updated_at_column="updated_at",
        observed_at_column=None,
        valid_from_column="valid_from",
        valid_to_column="valid_to",
        initial_valid_from=None,
        output_columns=("customer_id", "plan", "updated_at"),
        invalidate_hard_deletes=False,
    )

    with pytest.raises(RuntimeError, match=test_case.expected_error_fragment):
        with adapter.transaction(connection):
            statement: str
            for statement in statements:
                adapter.execute(connection, statement)

    rows_after_failure: tuple[tuple[object, ...], ...] = tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT customer_id, plan, CAST(valid_from AS VARCHAR), CAST(valid_to AS VARCHAR) "
            "FROM main.tx_target ORDER BY customer_id, valid_from"
        ).fetchall()
    )
    assert rows_after_failure == test_case.expected_rows_after_failure
