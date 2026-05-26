from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.adapters.bigquery.client import BigQueryAdapter
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.main.shared.helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
    build_qualified_table_name,
    build_read_all_sql,
)
from tests.unit.src.sqlbuild.compiler.fingerprints.main.shared.helpers._test_types import (
    BuildCreateTableSqlTestCase,
    BuildInsertSqlTestCase,
    BuildQualifiedTableNameTestCase,
    BuildReadAllSqlTestCase,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type

QUALIFIED_TABLE_NAME_TEST_CASES: list[BuildQualifiedTableNameTestCase] = [
    BuildQualifiedTableNameTestCase(
        description="builds schema-qualified name without database",
        database=None,
        schema="analytics",
        expected_name=f"analytics.{FINGERPRINT_TABLE_NAME}",
    ),
    BuildQualifiedTableNameTestCase(
        description="builds fully qualified name with database",
        database="warehouse",
        schema="analytics",
        expected_name=f"warehouse.analytics.{FINGERPRINT_TABLE_NAME}",
    ),
    BuildQualifiedTableNameTestCase(
        description="bigquery fingerprint table naming remains adapter-qualified",
        database="example-project",
        schema="dev",
        expected_name=f"`example-project.dev.{FINGERPRINT_TABLE_NAME}`",
    ),
]


READ_ALL_SQL_TEST_CASES: list[BuildReadAllSqlTestCase] = [
    BuildReadAllSqlTestCase(
        description="selects all fingerprint columns from qualified table",
        database=None,
        schema="staging",
        expected_contains=(
            "SELECT",
            "model_name",
            "target_database",
            "target_schema",
            "target_name",
            "run_id",
            "query_hash",
            "ast_hash",
            "schema_fingerprint",
            "query_sql",
            "ts",
            f"FROM staging.{FINGERPRINT_TABLE_NAME}",
        ),
    ),
    BuildReadAllSqlTestCase(
        description="uses fully qualified name when database provided",
        database="warehouse",
        schema="staging",
        expected_contains=(f"FROM warehouse.staging.{FINGERPRINT_TABLE_NAME}",),
    ),
]

INSERT_SQL_TEST_CASES: list[BuildInsertSqlTestCase] = [
    BuildInsertSqlTestCase(
        description="inserts all fingerprint values with inline literals",
        database=None,
        schema="marts",
        model_name="orders",
        target_database=None,
        target_schema="marts",
        target_name="orders",
        run_id="run_001",
        query_hash="abc123",
        ast_hash="def456",
        schema_fingerprint="ghi789",
        query_sql="SELECT id FROM orders",
        ts="2026-01-15T12:00:00",
        expected_contains=(
            "INSERT INTO",
            f"marts.{FINGERPRINT_TABLE_NAME}",
            "'orders'",
            "'marts'",
            "'run_001'",
            "'abc123'",
            "'def456'",
            "'ghi789'",
            "'U0VMRUNUIGlkIEZST00gb3JkZXJz'",
            "'2026-01-15T12:00:00'",
        ),
    ),
    BuildInsertSqlTestCase(
        description="renders null ast hash as SQL NULL",
        database=None,
        schema="marts",
        model_name="orders",
        target_database=None,
        target_schema="marts",
        target_name="orders",
        run_id="run_001",
        query_hash="abc123",
        ast_hash=None,
        schema_fingerprint="ghi789",
        query_sql="SELECT 1",
        ts="2026-01-15T12:00:00",
        expected_contains=("NULL",),
    ),
    BuildInsertSqlTestCase(
        description="escapes single quotes in query sql",
        database=None,
        schema="marts",
        model_name="orders",
        target_database=None,
        target_schema="marts",
        target_name="orders",
        run_id="run_001",
        query_hash="abc123",
        ast_hash=None,
        schema_fingerprint="ghi789",
        query_sql="SELECT * FROM t WHERE name = 'alice'",
        ts="2026-01-15T12:00:00",
        expected_contains=("U0VMRUNUICogRlJPTSB0IFdIRVJFIG5hbWUgPSAnYWxpY2Un",),
    ),
    BuildInsertSqlTestCase(
        description="stores multiline query sql as base64",
        database=None,
        schema="marts",
        model_name="orders",
        target_database=None,
        target_schema="marts",
        target_name="orders",
        run_id="run_001",
        query_hash="abc123",
        ast_hash=None,
        schema_fingerprint="ghi789",
        query_sql="SELECT '\\n' AS slash_n\nFROM orders\nWHERE note = 'line\\nvalue'",
        ts="2026-01-15T12:00:00",
        expected_contains=(
            "U0VMRUNUICdcbicgQVMgc2xhc2hfbgpGUk9NIG9yZGVycwpXSEVSRSBub3RlID0gJ2xpbmVcbnZhbHVlJw==",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    QUALIFIED_TABLE_NAME_TEST_CASES,
    ids=[case.description for case in QUALIFIED_TABLE_NAME_TEST_CASES],
)
def test_given_schema_when_building_qualified_name_then_returns_expected(
    test_case: BuildQualifiedTableNameTestCase,
) -> None:
    render_qualified_name: Callable[..., str | None] = (
        BigQueryAdapter().render_qualified_name
        if test_case.database == "example-project"
        else RENDER_QUALIFIED_NAME
    )
    result: str = build_qualified_table_name(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=render_qualified_name,
    )

    assert result == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    [
        BuildCreateTableSqlTestCase(
            description="contains create table if not exists with all columns",
            database=None,
            schema="analytics",
            expected_contains=(
                "CREATE TABLE IF NOT EXISTS",
                f"analytics.{FINGERPRINT_TABLE_NAME}",
                "model_name VARCHAR NOT NULL",
                "target_database VARCHAR,",
                "target_schema VARCHAR,",
                "target_name VARCHAR,",
                "run_id VARCHAR NOT NULL",
                "query_hash VARCHAR NOT NULL",
                "ast_hash VARCHAR,",
                "schema_fingerprint VARCHAR NOT NULL",
                "query_sql_b64 VARCHAR NOT NULL",
                "ts TIMESTAMP NOT NULL",
            ),
        ),
    ],
    ids=["contains create table if not exists with all columns"],
)
def test_given_schema_when_building_create_table_sql_then_contains_expected_fragments(
    test_case: BuildCreateTableSqlTestCase,
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
    READ_ALL_SQL_TEST_CASES,
    ids=[case.description for case in READ_ALL_SQL_TEST_CASES],
)
def test_given_schema_when_building_read_all_sql_then_contains_expected_fragments(
    test_case: BuildReadAllSqlTestCase,
) -> None:
    result: str = build_read_all_sql(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result


@pytest.mark.parametrize(
    "test_case",
    INSERT_SQL_TEST_CASES,
    ids=[case.description for case in INSERT_SQL_TEST_CASES],
)
def test_given_fingerprint_values_when_building_insert_sql_then_contains_expected_fragments(
    test_case: BuildInsertSqlTestCase,
) -> None:
    result: str = build_insert_sql(
        database=test_case.database,
        schema=test_case.schema,
        model_name=test_case.model_name,
        target_database=test_case.target_database,
        target_schema=test_case.target_schema,
        target_name=test_case.target_name,
        run_id=test_case.run_id,
        query_hash=test_case.query_hash,
        ast_hash=test_case.ast_hash,
        schema_fingerprint=test_case.schema_fingerprint,
        query_sql=test_case.query_sql,
        ts=test_case.ts,
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result
