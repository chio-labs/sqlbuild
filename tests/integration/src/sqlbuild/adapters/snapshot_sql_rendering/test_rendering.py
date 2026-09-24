"""Integration coverage for built-in adapter snapshot SQL rendering."""

from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.integration.src.sqlbuild.adapters.snapshot_sql_rendering._test_types import (
    SnapshotReappearanceRenderingTestCase,
    SnapshotSqlRenderingAdapterTestCase,
)

_REAPPEARANCE_GROUP_SEQUENCE_FRAGMENT: str = (
    "__observed_group_sequence AS (SELECT __observed_at, "
    "LAG(__observed_at) OVER (ORDER BY __observed_at) AS __prev_group_observed_at "
    "FROM (SELECT DISTINCT observed_at AS __observed_at FROM source_table)"
)
_REAPPEARANCE_APPLY_FRAGMENTS: tuple[str, ...] = (
    "__reappearances AS (SELECT __ordered.customer_id, "
    "MIN(__ordered.observed_at) AS __reappeared_at",
    "WHERE __latest.valid_to IS NOT NULL AND __ordered.observed_at > __latest.valid_to",
    "AND __present.observed_at = __latest.valid_to",
    "__new_changes AS (SELECT * FROM __changed_or_new UNION ALL SELECT __ordered.* "
    "FROM __ordered JOIN __reappearances",
    "AND __changed_or_new.observed_at = __ordered.observed_at",
)


@pytest.mark.parametrize(
    "test_case",
    [
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
                "SET valid_to = __close_candidates.__close_at FROM (WITH",
                "UNION ALL",
            ),
        ),
        SnapshotSqlRenderingAdapterTestCase(
            description="snowflake renders complete snapshot SQL matrix",
            adapter=SnowflakeAdapter(),
            expected_create_initial_fragments=(
                "CREATE OR REPLACE TRANSIENT TABLE target_table AS SELECT *",
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
                "SET valid_to = __close_candidates.__close_at FROM (WITH",
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
                "MERGE INTO target_table AS __target USING (WITH",
                "UNION ALL",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_builtin_adapter_when_rendering_snapshot_sql_then_covers_snapshot_matrix(
    test_case: SnapshotSqlRenderingAdapterTestCase,
) -> None:
    create_initial_sql: str = "\n".join(
        test_case.adapter.render_create_initial_snapshot_destination(
            table_type="transient",
            destination="target_table",
            origin="source_table",
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
            destination="target_table",
            origin="source_table",
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
        test_case.adapter.render_create_initial_historical_check_snapshot_destination(
            table_type="transient",
            destination="target_table",
            origin="source_table",
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
        test_case.adapter.render_create_initial_historical_timestamp_snapshot_destination(
            table_type="transient",
            destination="target_table",
            origin="source_table",
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
            destination="target_table",
            origin="source_table",
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
            destination="target_table",
            origin="source_table",
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


@pytest.mark.parametrize(
    "test_case",
    [
        SnapshotReappearanceRenderingTestCase(
            description="duckdb reopens reappearing historical check keys",
            adapter=DuckDbAdapter(),
            expected_initial_fragments=(
                _REAPPEARANCE_GROUP_SEQUENCE_FRAGMENT,
                "OR __prev_observed_at IS DISTINCT FROM __prev_group_observed_at",
            ),
            expected_apply_fragments=_REAPPEARANCE_APPLY_FRAGMENTS,
            unexpected_apply_fragments=("UNION DISTINCT",),
        ),
        SnapshotReappearanceRenderingTestCase(
            description="motherduck reopens reappearing historical check keys",
            adapter=MotherDuckAdapter(),
            expected_initial_fragments=(
                _REAPPEARANCE_GROUP_SEQUENCE_FRAGMENT,
                "OR __prev_observed_at IS DISTINCT FROM __prev_group_observed_at",
            ),
            expected_apply_fragments=_REAPPEARANCE_APPLY_FRAGMENTS,
            unexpected_apply_fragments=("UNION DISTINCT",),
        ),
        SnapshotReappearanceRenderingTestCase(
            description="postgres reopens reappearing historical check keys without qualify",
            adapter=PostgresAdapter(),
            expected_initial_fragments=(
                _REAPPEARANCE_GROUP_SEQUENCE_FRAGMENT,
                "OR __prev_observed_at IS DISTINCT FROM __prev_group_observed_at",
            ),
            expected_apply_fragments=(
                *_REAPPEARANCE_APPLY_FRAGMENTS,
                ") AS __rn FROM target_table) AS __q WHERE __rn = 1)",
            ),
            unexpected_apply_fragments=("QUALIFY", "UNION DISTINCT"),
        ),
        SnapshotReappearanceRenderingTestCase(
            description="sqlserver reopens reappearing historical check keys without qualify",
            adapter=SqlServerAdapter(),
            expected_initial_fragments=(
                _REAPPEARANCE_GROUP_SEQUENCE_FRAGMENT,
                "OR (__prev_observed_at <> __prev_group_observed_at "
                "OR (__prev_observed_at IS NULL AND __prev_group_observed_at IS NOT NULL) "
                "OR (__prev_observed_at IS NOT NULL AND __prev_group_observed_at IS NULL))",
            ),
            expected_apply_fragments=(
                *_REAPPEARANCE_APPLY_FRAGMENTS,
                "__latest AS (SELECT * FROM __latest_ordered WHERE __rn = 1)",
            ),
            unexpected_apply_fragments=("QUALIFY", "UNION DISTINCT", "IS DISTINCT FROM"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_hard_deletes_when_rendering_historical_check_snapshot_then_reopens_reappearing_keys(
    test_case: SnapshotReappearanceRenderingTestCase,
) -> None:
    initial_sql: str = "\n".join(
        test_case.adapter.render_create_initial_historical_check_snapshot_destination(
            table_type="table",
            destination="target_table",
            origin="source_table",
            unique_key=("customer_id",),
            check_columns=("plan",),
            observed_at_column="observed_at",
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "observed_at"),
            invalidate_hard_deletes=True,
        )
    )
    apply_statements: tuple[str, ...] = (
        test_case.adapter.render_apply_historical_check_snapshot_changes(
            destination="target_table",
            origin="source_table",
            unique_key=("customer_id",),
            check_columns=("plan",),
            observed_at_column="observed_at",
            valid_from_column="valid_from",
            valid_to_column="valid_to",
            output_columns=("customer_id", "plan", "observed_at"),
            invalidate_hard_deletes=True,
        )
    )
    without_hard_deletes_sql: str = "\n".join(
        (
            *test_case.adapter.render_create_initial_historical_check_snapshot_destination(
                table_type="table",
                destination="target_table",
                origin="source_table",
                unique_key=("customer_id",),
                check_columns=("plan",),
                observed_at_column="observed_at",
                valid_from_column="valid_from",
                valid_to_column="valid_to",
                output_columns=("customer_id", "plan", "observed_at"),
                invalidate_hard_deletes=False,
            ),
            *test_case.adapter.render_apply_historical_check_snapshot_changes(
                destination="target_table",
                origin="source_table",
                unique_key=("customer_id",),
                check_columns=("plan",),
                observed_at_column="observed_at",
                valid_from_column="valid_from",
                valid_to_column="valid_to",
                output_columns=("customer_id", "plan", "observed_at"),
                invalidate_hard_deletes=False,
            ),
        )
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_initial_fragments:
        assert expected_fragment in initial_sql
    statement: str
    for statement in apply_statements:
        for expected_fragment in test_case.expected_apply_fragments:
            assert expected_fragment in statement
        unexpected_fragment: str
        for unexpected_fragment in test_case.unexpected_apply_fragments:
            assert unexpected_fragment not in statement
    assert "__prev_group_observed_at" not in without_hard_deletes_sql
    assert "__reappearances" not in without_hard_deletes_sql
