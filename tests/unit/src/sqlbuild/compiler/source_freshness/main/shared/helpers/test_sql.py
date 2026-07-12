from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.adapter.types import FrameworkType
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.compiler.source_freshness.helpers.sql import (
    build_create_table_sql,
    build_qualified_table_name,
    build_read_latest_sql,
)
from tests.unit.src.sqlbuild.compiler.source_freshness.main.shared.helpers._test_types import (
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
    ids=lambda case: case.description,
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
        ),
        BuildSourceFreshnessSqlTestCase(
            description="emits transient table when requested",
            database=None,
            schema="analytics",
            transient=True,
            expected_contains=(
                "CREATE TRANSIENT TABLE IF NOT EXISTS",
                f"analytics.{SOURCE_FRESHNESS_TABLE_NAME}",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_when_building_create_table_sql_then_contains_expected_fragments(
    test_case: BuildSourceFreshnessSqlTestCase,
) -> None:
    result: str = build_create_table_sql(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
        render_framework_type=RENDER_FRAMEWORK_TYPE,
        transient=test_case.transient,
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
    ids=lambda case: case.description,
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
