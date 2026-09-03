"""Adapter contract tests for direct microbatch state SQL."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from sqlbuild.microbatches._helpers.sql import (
    build_create_table_sql,
    build_insert_many_sql,
    build_insert_sql,
    build_read_scope_sql,
)
from sqlbuild.microbatches.constants import MICROBATCH_COLUMNS, MICROBATCH_TABLE_NAME
from sqlbuild.microbatches.main.deterministic_event_id import (
    deterministic_microbatch_event_id,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
from sqlbuild.microbatches.types import MicrobatchRecordType
from tests.unit.src.sqlbuild.microbatches._test_types import (
    MicrobatchDdlAdapterTestCase,
    MicrobatchSqlBehaviorTestCase,
)
from tests.unit.src.sqlbuild.microbatches.helpers import (
    SCOPE,
    completion_for_sql,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchDdlAdapterTestCase(
            description="duckdb", adapter=DuckDbAdapter(), expected_table_name=MICROBATCH_TABLE_NAME
        ),
        MicrobatchDdlAdapterTestCase(
            description="snowflake",
            adapter=SnowflakeAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="bigquery",
            adapter=BigQueryAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="databricks",
            adapter=DatabricksAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="postgres",
            adapter=PostgresAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="sqlserver",
            adapter=SqlServerAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_builtin_adapter_when_building_state_ddl_then_all_columns_are_declared(
    test_case: MicrobatchDdlAdapterTestCase,
) -> None:
    adapter: BaseAdapter = test_case.adapter
    sql: str = build_create_table_sql(
        database="warehouse",
        schema="analytics",
        render_qualified_name=adapter.render_qualified_name,
        render_framework_type=adapter.render_framework_type,
    )

    assert "CREATE TABLE IF NOT EXISTS" in sql
    assert test_case.expected_table_name in sql
    for column in MICROBATCH_COLUMNS:
        assert column in sql
    assert "rows_affected BIGINT" in sql
    assert "observed_row_count BIGINT" in sql


@pytest.mark.parametrize(
    "test_case",
    [MicrobatchSqlBehaviorTestCase(description="sqlserver guard", expected_statement_count=1)],
    ids=lambda case: case.description,
)
def test_given_sqlserver_adapter_when_rendering_state_ddl_then_uses_supported_guard(
    test_case: MicrobatchSqlBehaviorTestCase,
) -> None:
    sql: str = SqlServerAdapter().render_create_microbatch_state_table_sql(
        database="warehouse", schema="analytics"
    )

    assert sql.startswith("IF NOT EXISTS (SELECT 1 FROM information_schema.tables")
    assert "CREATE TABLE warehouse.analytics._sqlbuild_microbatches" in sql
    assert "CREATE TABLE IF NOT EXISTS" not in sql
    assert len((sql,)) == test_case.expected_statement_count


@pytest.mark.parametrize(
    "test_case",
    [MicrobatchSqlBehaviorTestCase(description="indexed access paths", expected_statement_count=5)],
    ids=lambda case: case.description,
)
def test_given_indexed_adapter_when_rendering_state_indexes_then_all_access_paths_are_covered(
    test_case: MicrobatchSqlBehaviorTestCase,
) -> None:
    sqls: tuple[str, ...] = DuckDbAdapter().render_create_microbatch_state_index_sqls(
        database=None, schema="analytics"
    )

    assert len(sqls) == test_case.expected_statement_count
    assert all("CREATE INDEX IF NOT EXISTS" in sql for sql in sqls)
    assert any("scope_kind" in sql and "physical_generation_id" in sql for sql in sqls)
    assert any("replay_requirement_id" in sql for sql in sqls)
    assert any("partition_start" in sql and "partition_end" in sql for sql in sqls)


@pytest.mark.parametrize(
    "test_case",
    [MicrobatchSqlBehaviorTestCase(description="completion insert", expected_statement_count=1)],
    ids=lambda case: case.description,
)
def test_given_completion_when_building_insert_then_provenance_and_numeric_rows_are_encoded(
    test_case: MicrobatchSqlBehaviorTestCase,
) -> None:
    event: MicrobatchEvent = completion_for_sql()

    sql: str = build_insert_sql(
        event=event, render_qualified_name=DuckDbAdapter().render_qualified_name
    )

    assert "INSERT INTO analytics._sqlbuild_microbatches" in sql
    assert "'partition_completion'" in sql
    assert "'replay_on_change'" in sql
    assert "'recovery'" in sql
    assert "'F2'" in sql
    assert "'fingerprint''definition'" in sql
    assert "CAST(0 AS BIGINT)" in sql
    assert len((sql,)) == test_case.expected_statement_count


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchDdlAdapterTestCase(
            description="duckdb", adapter=DuckDbAdapter(), expected_table_name=MICROBATCH_TABLE_NAME
        ),
        MicrobatchDdlAdapterTestCase(
            description="snowflake",
            adapter=SnowflakeAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="bigquery",
            adapter=BigQueryAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="databricks",
            adapter=DatabricksAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="postgres",
            adapter=PostgresAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
        MicrobatchDdlAdapterTestCase(
            description="sqlserver",
            adapter=SqlServerAdapter(),
            expected_table_name=MICROBATCH_TABLE_NAME,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_builtin_adapter_when_rendering_direct_event_inserts_then_typed_columns_are_cast(
    test_case: MicrobatchDdlAdapterTestCase,
) -> None:
    event: MicrobatchEvent = completion_for_sql()

    single_sql: str = build_insert_sql(
        event=event, render_qualified_name=test_case.adapter.render_qualified_name
    )
    bulk_sql: str = build_insert_many_sql(
        events=(event, replace(event, event_id="second-event")),
        render_qualified_name=test_case.adapter.render_qualified_name,
    )

    for sql, expected_row_count in ((single_sql, 1), (bulk_sql, 2)):
        assert test_case.expected_table_name in sql
        assert "CAST('2026-01-01T00:00:00' AS TIMESTAMP)" in sql
        assert sql.count("CAST(NULL AS TIMESTAMP)") == 4 * expected_row_count
        assert sql.count("CAST(0 AS BIGINT)") == expected_row_count
        assert sql.count("CAST(NULL AS BIGINT)") == expected_row_count


@pytest.mark.parametrize(
    "test_case",
    [MicrobatchSqlBehaviorTestCase(description="generation filters", expected_statement_count=2)],
    ids=lambda case: case.description,
)
def test_given_wildcard_and_concrete_generations_when_reading_then_filter_is_optional(
    test_case: MicrobatchSqlBehaviorTestCase,
) -> None:
    scope: MicrobatchScope = completion_for_sql().scope

    wildcard_sql: str = build_read_scope_sql(
        scope=scope, render_qualified_name=DuckDbAdapter().render_qualified_name
    )
    concrete_sql: str = build_read_scope_sql(
        scope=MicrobatchScope(
            scope_kind=scope.scope_kind,
            scope_key=scope.scope_key,
            model_name=scope.model_name,
            target_database=scope.target_database,
            target_schema=scope.target_schema,
            target_name=scope.target_name,
            physical_generation_id="generation-1",
        ),
        render_qualified_name=DuckDbAdapter().render_qualified_name,
    )

    assert "physical_generation_id =" not in wildcard_sql
    assert "physical_generation_id = 'generation-1'" in concrete_sql
    assert wildcard_sql.endswith("ORDER BY created_at, event_id")
    assert len((wildcard_sql, concrete_sql)) == test_case.expected_statement_count


@pytest.mark.parametrize(
    "test_case",
    [
        MicrobatchSqlBehaviorTestCase(
            description="deterministic identity", expected_statement_count=4
        )
    ],
    ids=lambda case: case.description,
)
def test_given_logical_event_identity_when_constructing_ids_then_ids_are_stable_and_distinct(
    test_case: MicrobatchSqlBehaviorTestCase,
) -> None:
    first: str = deterministic_microbatch_event_id(
        scope=SCOPE,
        record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
        partition_start="1",
        partition_end="2",
        completion_reason="completion_history_missing:synthesize",
    )
    independent: str = deterministic_microbatch_event_id(
        scope=SCOPE,
        record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
        partition_start="1",
        partition_end="2",
        completion_reason="completion_history_missing:synthesize",
    )
    distinct: tuple[str, ...] = (
        first,
        deterministic_microbatch_event_id(
            scope=SCOPE,
            record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
            partition_start="2",
            partition_end="3",
            completion_reason="completion_history_missing:synthesize",
        ),
        deterministic_microbatch_event_id(
            scope=SCOPE,
            record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
            partition_start="1",
            partition_end="2",
            completion_reason="completion_history_missing:recover_empty",
        ),
        deterministic_microbatch_event_id(
            scope=replace(SCOPE, physical_generation_id="generation-2"),
            record_type=MicrobatchRecordType.SYNTHETIC_COMPLETION,
            partition_start="1",
            partition_end="2",
            completion_reason="completion_history_missing:synthesize",
        ),
    )

    assert first == independent
    assert len(set(distinct)) == test_case.expected_statement_count
