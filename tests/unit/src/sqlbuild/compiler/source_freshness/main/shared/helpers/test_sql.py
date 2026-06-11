from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.main.shared.helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
    build_qualified_table_name,
    build_read_latest_sql,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.shared.helpers._test_types import (
    BuildSourceFreshnessInsertSqlTestCase,
    BuildSourceFreshnessSqlTestCase,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSourceFreshnessSqlTestCase(
            description="builds schema-qualified source freshness table name",
            database=None,
            schema="analytics",
            expected_contains=(f"analytics.{SOURCE_FRESHNESS_TABLE_NAME}",),
        )
    ],
    ids=["builds schema-qualified source freshness table name"],
)
def test_given_schema_when_building_qualified_name_then_returns_expected(
    test_case: BuildSourceFreshnessSqlTestCase,
) -> None:
    result: str = build_qualified_table_name(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSourceFreshnessSqlTestCase(
            description="contains create table if not exists with all source freshness columns",
            database=None,
            schema="analytics",
            expected_contains=(
                "CREATE TABLE IF NOT EXISTS",
                f"analytics.{SOURCE_FRESHNESS_TABLE_NAME}",
                "source_name VARCHAR NOT NULL",
                "target_database VARCHAR,",
                "target_schema VARCHAR,",
                "target_name VARCHAR,",
                "run_id VARCHAR NOT NULL",
                "strategy VARCHAR NOT NULL",
                "value_kind VARCHAR NOT NULL",
                "data_version VARCHAR,",
                "data_version_hash VARCHAR NOT NULL",
                "observed_at TIMESTAMP NOT NULL",
            ),
        )
    ],
    ids=["contains create table if not exists with all source freshness columns"],
)
def test_given_schema_when_building_create_table_sql_then_contains_expected_fragments(
    test_case: BuildSourceFreshnessSqlTestCase,
) -> None:
    result: str = build_create_table_sql(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSourceFreshnessSqlTestCase(
            description="selects latest source freshness rows with window ranking",
            database=None,
            schema="analytics",
            expected_contains=(
                "ROW_NUMBER() OVER",
                "PARTITION BY source_name, target_database, target_schema, target_name",
                "ORDER BY observed_at DESC, run_id DESC",
                f"FROM analytics.{SOURCE_FRESHNESS_TABLE_NAME}",
                "WHERE __sqlbuild_latest_rank = 1",
            ),
        )
    ],
    ids=["selects latest source freshness rows with window ranking"],
)
def test_given_schema_when_building_read_latest_sql_then_contains_windowed_latest_query(
    test_case: BuildSourceFreshnessSqlTestCase,
) -> None:
    result: str = build_read_latest_sql(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSourceFreshnessInsertSqlTestCase(
            description="inserts source freshness values with escaped inline literals",
            database=None,
            schema="analytics",
            source_name="raw.orders",
            target_database=None,
            target_schema="raw",
            target_name="orders",
            run_id="run_001",
            strategy="adapter_metadata",
            value_kind="timestamp",
            data_version="2026-01-15T12:00:00",
            data_version_hash="hash'a",
            observed_at="2026-01-15T12:05:00",
            expected_contains=(
                "INSERT INTO",
                f"analytics.{SOURCE_FRESHNESS_TABLE_NAME}",
                "'raw.orders'",
                "NULL",
                "'raw'",
                "'orders'",
                "'run_001'",
                "'adapter_metadata'",
                "'timestamp'",
                "'2026-01-15T12:00:00'",
                "'hash''a'",
                "'2026-01-15T12:05:00'",
            ),
        )
    ],
    ids=["inserts source freshness values with escaped inline literals"],
)
def test_given_source_freshness_values_when_building_insert_sql_then_contains_expected_fragments(
    test_case: BuildSourceFreshnessInsertSqlTestCase,
) -> None:
    result: str = build_insert_sql(
        database=test_case.database,
        schema=test_case.schema,
        source_name=test_case.source_name,
        target_database=test_case.target_database,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        run_id=test_case.run_id,
        strategy=test_case.strategy,
        value_kind=test_case.value_kind,
        data_version=test_case.data_version,
        data_version_hash=test_case.data_version_hash,
        observed_at=test_case.observed_at,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result
