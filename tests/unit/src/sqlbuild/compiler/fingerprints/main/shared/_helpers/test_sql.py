from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.fingerprints._helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
    build_qualified_table_name,
    build_read_latest_sql,
)
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.fingerprints.models import Fingerprint
from tests.unit.src.sqlbuild.compiler.fingerprints.main.shared._helpers._test_types import (
    BuildCreateTableSqlTestCase,
    BuildInsertSqlTestCase,
    BuildQualifiedTableNameTestCase,
)

RENDER_QUALIFIED_NAME: Callable[..., str | None] = DuckDbAdapter().render_qualified_name
RENDER_FRAMEWORK_TYPE: Callable[[FrameworkType], str] = DuckDbAdapter().render_framework_type


@pytest.mark.parametrize(
    "test_case",
    [
        BuildQualifiedTableNameTestCase(
            description="builds schema-qualified name without database",
            database=None,
            schema="analytics",
            render_qualified_name=RENDER_QUALIFIED_NAME,
            expected_name=f"analytics.{FINGERPRINT_TABLE_NAME}",
        ),
        BuildQualifiedTableNameTestCase(
            description="builds fully qualified name with database",
            database="warehouse",
            schema="analytics",
            render_qualified_name=RENDER_QUALIFIED_NAME,
            expected_name=f"warehouse.analytics.{FINGERPRINT_TABLE_NAME}",
        ),
        BuildQualifiedTableNameTestCase(
            description="bigquery fingerprint table naming remains adapter-qualified",
            database="example-project",
            schema="dev",
            render_qualified_name=BigQueryAdapter().render_qualified_name,
            expected_name=f"`example-project.dev.{FINGERPRINT_TABLE_NAME}`",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_when_building_qualified_name_then_returns_expected(
    test_case: BuildQualifiedTableNameTestCase,
) -> None:
    result: str = build_qualified_table_name(
        database=test_case.database,
        schema=test_case.schema,
        render_qualified_name=test_case.render_qualified_name,
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
                "node_type VARCHAR NOT NULL",
                "node_name VARCHAR NOT NULL",
                "target_database VARCHAR,",
                "target_schema VARCHAR,",
                "target_name VARCHAR,",
                "run_id VARCHAR NOT NULL",
                "definition_hash VARCHAR NOT NULL",
                "schema_fingerprint VARCHAR NOT NULL",
                "definition_b64 VARCHAR NOT NULL",
                "metadata_json_b64 VARCHAR NOT NULL",
                "ts TIMESTAMP NOT NULL",
            ),
        ),
        BuildCreateTableSqlTestCase(
            description="emits transient table when requested",
            database=None,
            schema="analytics",
            transient=True,
            expected_contains=(
                "CREATE TRANSIENT TABLE IF NOT EXISTS",
                f"analytics.{FINGERPRINT_TABLE_NAME}",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_when_building_create_table_sql_then_contains_expected_fragments(
    test_case: BuildCreateTableSqlTestCase,
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
        BuildCreateTableSqlTestCase(
            description="selects latest fingerprint rows with window ranking",
            database=None,
            schema="staging",
            expected_contains=(
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY ts DESC, run_id DESC",
                f"FROM staging.{FINGERPRINT_TABLE_NAME}",
                "WHERE __sqlbuild_latest_rank = 1",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_schema_when_building_read_latest_sql_then_contains_windowed_latest_query(
    test_case: BuildCreateTableSqlTestCase,
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
        BuildInsertSqlTestCase(
            description="inserts all fingerprint values with inline literals",
            database=None,
            schema="marts",
            node_type="model",
            node_name="orders",
            target_database=None,
            target_schema="marts",
            target_name="orders",
            run_id="run_001",
            definition_hash="abc123",
            version_hash="def456",
            schema_fingerprint="ghi789",
            definition="SELECT id FROM orders",
            metadata_json='{"config":{"materialized":"table"}}',
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
                "'eyJjb25maWciOnsibWF0ZXJpYWxpemVkIjoidGFibGUifX0='",
                "'2026-01-15T12:00:00'",
            ),
        ),
        BuildInsertSqlTestCase(
            description="escapes single quotes in query sql",
            database=None,
            schema="marts",
            node_type="model",
            node_name="orders",
            target_database=None,
            target_schema="marts",
            target_name="orders",
            run_id="run_001",
            definition_hash="abc123",
            version_hash="def456",
            schema_fingerprint="ghi789",
            definition="SELECT * FROM t WHERE name = 'alice'",
            metadata_json="{}",
            ts="2026-01-15T12:00:00",
            expected_contains=("U0VMRUNUICogRlJPTSB0IFdIRVJFIG5hbWUgPSAnYWxpY2Un",),
        ),
        BuildInsertSqlTestCase(
            description="stores multiline query sql as base64",
            database=None,
            schema="marts",
            node_type="model",
            node_name="orders",
            target_database=None,
            target_schema="marts",
            target_name="orders",
            run_id="run_001",
            definition_hash="abc123",
            version_hash="def456",
            schema_fingerprint="ghi789",
            definition="SELECT '\\n' AS slash_n\nFROM orders\nWHERE note = 'line\\nvalue'",
            metadata_json="{}",
            ts="2026-01-15T12:00:00",
            expected_contains=(
                "U0VMRUNUICdcbicgQVMgc2xhc2hfbgpGUk9NIG9yZGVycwpXSEVSRSBub3RlID0gJ2xpbmVcbnZhbHVlJw==",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_fingerprint_values_when_building_insert_sql_then_contains_expected_fragments(
    test_case: BuildInsertSqlTestCase,
) -> None:
    result: str = build_insert_sql(
        database=test_case.database,
        schema=test_case.schema,
        fingerprint=Fingerprint(
            node_type=test_case.node_type,
            node_name=test_case.node_name,
            target_database=test_case.target_database,
            target_schema=test_case.target_schema,
            target_name=test_case.target_name,
            run_id=test_case.run_id,
            definition_hash=test_case.definition_hash,
            version_hash=test_case.version_hash,
            schema_fingerprint=test_case.schema_fingerprint,
            definition=test_case.definition,
            metadata_json=test_case.metadata_json,
            ts=datetime.fromisoformat(test_case.ts),
        ),
        render_qualified_name=RENDER_QUALIFIED_NAME,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result
