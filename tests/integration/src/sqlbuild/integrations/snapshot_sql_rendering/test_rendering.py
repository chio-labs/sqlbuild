"""Integration coverage for built-in adapter snapshot SQL rendering."""

from __future__ import annotations

import pytest

from sqlbuild.integrations.bigquery.client import BigQueryAdapter
from sqlbuild.integrations.databricks.client import DatabricksAdapter
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.integrations.snowflake.client import SnowflakeAdapter
from tests.integration.src.sqlbuild.integrations.snapshot_sql_rendering._test_types import (
    SnapshotSqlRenderingAdapterTestCase,
)

SNAPSHOT_SQL_RENDERING_ADAPTER_TEST_CASES: list[SnapshotSqlRenderingAdapterTestCase] = [
    SnapshotSqlRenderingAdapterTestCase(
        description="duckdb renders complete snapshot SQL matrix",
        adapter=DuckDbAdapter(),
        expected_create_initial_fragments=(
            "CREATE OR REPLACE TABLE target_table AS SELECT *",
            "updated_at AS valid_from",
            "CAST(NULL AS TIMESTAMP) AS valid_to",
        ),
        expected_timestamp_hard_delete_fragments=(
            "UPDATE target_table AS __target SET effective_to = __source.updated_at",
            "__target.customer_id = __source.customer_id",
            "__target.region = __source.region",
            "WHERE __target.effective_to IS NULL AND NOT EXISTS",
        ),
        expected_historical_check_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "NOT EXISTS",
        ),
        expected_historical_timestamp_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "NOT EXISTS",
        ),
        expected_historical_timestamp_apply_hard_delete_fragments=(
            "__hard_deletes AS (",
            "AS __close_at FROM target_table AS __target",
            "UNION ALL",
        ),
        expected_historical_check_apply_fragments=(
            "LAG(plan) OVER (PARTITION BY customer_id ORDER BY observed_at)",
            "__hard_deletes AS (",
            "INSERT INTO target_table (customer_id, plan, observed_at, valid_from, valid_to)",
            "SET valid_to = (SELECT MIN(__close_candidates.__close_at)",
            "UNION ALL",
        ),
    ),
    SnapshotSqlRenderingAdapterTestCase(
        description="bigquery renders complete snapshot SQL matrix",
        adapter=BigQueryAdapter(),
        expected_create_initial_fragments=(
            "CREATE OR REPLACE TABLE `target_table` AS SELECT *",
            "updated_at AS valid_from",
            "CAST(NULL AS TIMESTAMP) AS valid_to",
        ),
        expected_timestamp_hard_delete_fragments=(
            "UPDATE target_table AS __target SET effective_to = __source.updated_at",
            "__target.customer_id = __source.customer_id",
            "__target.region = __source.region",
            "WHERE __target.effective_to IS NULL AND NOT EXISTS",
        ),
        expected_historical_check_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "__hard_delete_candidates AS (",
        ),
        expected_historical_timestamp_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "__hard_delete_candidates AS (",
        ),
        expected_historical_timestamp_apply_hard_delete_fragments=(
            "__hard_deletes AS (",
            "AS __close_at FROM target_table AS __target",
            "UNION ALL",
        ),
        expected_historical_check_apply_fragments=(
            "LAG(plan) OVER (PARTITION BY customer_id ORDER BY observed_at)",
            "__hard_deletes AS (",
            "INSERT INTO target_table (customer_id, plan, observed_at, valid_from, valid_to)",
            "SET valid_to = (SELECT MIN(__close_candidates.__close_at)",
            "UNION ALL",
        ),
    ),
    SnapshotSqlRenderingAdapterTestCase(
        description="snowflake renders complete snapshot SQL matrix",
        adapter=SnowflakeAdapter(),
        expected_create_initial_fragments=(
            "CREATE OR REPLACE TABLE target_table AS SELECT *",
            "updated_at AS valid_from",
            "CAST(NULL AS TIMESTAMP) AS valid_to",
        ),
        expected_timestamp_hard_delete_fragments=(
            "UPDATE target_table AS __target SET effective_to = __source.updated_at",
            "__target.customer_id = __source.customer_id",
            "__target.region = __source.region",
            "WHERE __target.effective_to IS NULL AND NOT EXISTS",
        ),
        expected_historical_check_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "__hard_delete_candidates AS (",
        ),
        expected_historical_timestamp_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "__hard_delete_candidates AS (",
        ),
        expected_historical_timestamp_apply_hard_delete_fragments=(
            "__hard_deletes AS (",
            "AS __close_at FROM target_table AS __target",
            "UNION ALL",
        ),
        expected_historical_check_apply_fragments=(
            "LAG(plan) OVER (PARTITION BY customer_id ORDER BY observed_at)",
            "__hard_deletes AS (",
            "INSERT INTO target_table (customer_id, plan, observed_at, valid_from, valid_to)",
            "SET valid_to = (SELECT MIN(__close_candidates.__close_at)",
            "UNION ALL",
        ),
    ),
    SnapshotSqlRenderingAdapterTestCase(
        description="databricks renders complete snapshot SQL matrix",
        adapter=DatabricksAdapter(),
        expected_create_initial_fragments=(
            "CREATE OR REPLACE TABLE target_table AS SELECT *",
            "updated_at AS valid_from",
            "CAST(NULL AS TIMESTAMP) AS valid_to",
        ),
        expected_timestamp_hard_delete_fragments=(
            "MERGE INTO target_table AS __target USING source_table AS __source",
            "__target.customer_id = __source.customer_id",
            "__target.region = __source.region",
            "WHEN MATCHED THEN UPDATE SET effective_to = __source.updated_at",
        ),
        expected_historical_check_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "__hard_delete_candidates AS (",
        ),
        expected_historical_timestamp_initial_hard_delete_fragments=(
            "__hard_deleted_at",
            "WHEN __hard_deleted_at < __next_change_at THEN __hard_deleted_at",
            "__hard_delete_candidates AS (",
        ),
        expected_historical_timestamp_apply_hard_delete_fragments=(
            "__hard_deletes AS (",
            "AS __close_at FROM target_table AS __target",
            "UNION ALL",
        ),
        expected_historical_check_apply_fragments=(
            "LAG(plan) OVER (PARTITION BY customer_id ORDER BY observed_at)",
            "__hard_deletes AS (",
            "INSERT INTO target_table (customer_id, plan, observed_at, valid_from, valid_to)",
            "SET valid_to = (SELECT MIN(__close_candidates.__close_at)",
            "UNION ALL",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    SNAPSHOT_SQL_RENDERING_ADAPTER_TEST_CASES,
    ids=[case.description for case in SNAPSHOT_SQL_RENDERING_ADAPTER_TEST_CASES],
)
def test_given_builtin_adapter_when_rendering_snapshot_sql_then_covers_snapshot_matrix(
    test_case: SnapshotSqlRenderingAdapterTestCase,
) -> None:
    create_initial_sql: str = "\n".join(
        test_case.adapter.render_create_initial_snapshot_target(
            target="target_table",
            source="source_table",
            snapshot_strategy="timestamp",
            updated_at_column="updated_at",
            observed_at_column=None,
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            initial_valid_from=None,
        )
    )
    timestamp_hard_delete_sql: str = "\n".join(
        test_case.adapter.render_apply_timestamp_snapshot_changes(
            target="target_table",
            source="source_table",
            unique_key=("customer_id", "region"),
            updated_at_column="updated_at",
            observed_at_column=None,
            valid_from_column="effective_from",
            valid_to_column="effective_to",
            initial_valid_from=None,
            output_columns=("customer_id", "region", "plan", "updated_at"),
            invalidate_hard_deletes=True,
        )
    )
    historical_check_initial_sql: str = "\n".join(
        test_case.adapter.render_create_initial_historical_check_snapshot_target(
            target="target_table",
            source="source_table",
            unique_key=("customer_id",),
            check_columns=("plan",),
            observed_at_column="observed_at",
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "observed_at"),
            invalidate_hard_deletes=True,
        )
    )
    historical_timestamp_initial_sql: str = "\n".join(
        test_case.adapter.render_create_initial_historical_timestamp_snapshot_target(
            target="target_table",
            source="source_table",
            unique_key=("customer_id",),
            updated_at_column="updated_at",
            observed_at_column="observed_at",
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "updated_at", "observed_at"),
            invalidate_hard_deletes=True,
        )
    )
    historical_timestamp_apply_sql: str = "\n".join(
        test_case.adapter.render_apply_historical_timestamp_snapshot_changes(
            target="target_table",
            source="source_table",
            unique_key=("customer_id",),
            updated_at_column="updated_at",
            observed_at_column="observed_at",
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "updated_at", "observed_at"),
            invalidate_hard_deletes=True,
        )
    )
    historical_check_apply_sql: str = "\n".join(
        test_case.adapter.render_apply_historical_check_snapshot_changes(
            target="target_table",
            source="source_table",
            unique_key=("customer_id",),
            check_columns=("plan",),
            observed_at_column="observed_at",
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "observed_at"),
            invalidate_hard_deletes=True,
        )
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_create_initial_fragments:
        assert expected_fragment in create_initial_sql
    for expected_fragment in test_case.expected_timestamp_hard_delete_fragments:
        assert expected_fragment in timestamp_hard_delete_sql
    for expected_fragment in test_case.expected_historical_check_initial_hard_delete_fragments:
        assert expected_fragment in historical_check_initial_sql
    for expected_fragment in test_case.expected_historical_timestamp_initial_hard_delete_fragments:
        assert expected_fragment in historical_timestamp_initial_sql
    for expected_fragment in test_case.expected_historical_timestamp_apply_hard_delete_fragments:
        assert expected_fragment in historical_timestamp_apply_sql
    for expected_fragment in test_case.expected_historical_check_apply_fragments:
        assert expected_fragment in historical_check_apply_sql
