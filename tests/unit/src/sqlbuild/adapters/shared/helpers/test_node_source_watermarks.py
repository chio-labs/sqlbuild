from __future__ import annotations

from datetime import datetime

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.adapters.shared.helpers.node_source_watermarks import (
    render_create_node_source_watermark_table_sql,
    render_insert_node_source_watermark_records_sql,
    render_read_latest_node_source_watermarks_sql,
)
from sqlbuild.compiler.node_source_watermarks.constants import (
    NODE_SOURCE_WATERMARK_TABLE_NAME,
)
from sqlbuild.compiler.node_source_watermarks.main.encode_payload import (
    encode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkPayload,
    NodeSourceWatermarkRecord,
    SourceWatermarkEntry,
)
from tests.unit.src.sqlbuild.adapters.shared.helpers._test_types import (
    RenderNodeSourceWatermarkSqlTestCase,
)

ADAPTER: DuckDbAdapter = DuckDbAdapter()


@pytest.mark.parametrize(
    "test_case",
    [
        RenderNodeSourceWatermarkSqlTestCase(
            description="creates table with payload column",
            expected_contains=(
                "CREATE TABLE IF NOT EXISTS",
                f"analytics.{NODE_SOURCE_WATERMARK_TABLE_NAME}",
                "node_type VARCHAR NOT NULL",
                "node_name VARCHAR NOT NULL",
                "node_version_hash VARCHAR NOT NULL",
                "watermarks_json_b64 VARCHAR NOT NULL",
                "created_at TIMESTAMP NOT NULL",
            ),
        )
    ],
    ids=["creates table with payload column"],
)
def test_given_schema_when_rendering_create_sql_then_contains_watermark_columns(
    test_case: RenderNodeSourceWatermarkSqlTestCase,
) -> None:
    result: str = render_create_node_source_watermark_table_sql(
        database=None,
        schema="analytics",
        render_qualified_name=ADAPTER.render_qualified_name,
        render_framework_type=ADAPTER.render_framework_type,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result


@pytest.mark.parametrize(
    "test_case",
    [
        RenderNodeSourceWatermarkSqlTestCase(
            description="reads latest row per node identity",
            expected_contains=(
                "ROW_NUMBER() OVER",
                "PARTITION BY node_type, node_name",
                "ORDER BY created_at DESC, run_id DESC",
                f"FROM analytics.{NODE_SOURCE_WATERMARK_TABLE_NAME}",
            ),
        )
    ],
    ids=["reads latest row per node identity"],
)
def test_given_schema_when_rendering_latest_read_sql_then_partitions_by_node_identity(
    test_case: RenderNodeSourceWatermarkSqlTestCase,
) -> None:
    result: str = render_read_latest_node_source_watermarks_sql(
        database=None,
        schema="analytics",
        render_qualified_name=ADAPTER.render_qualified_name,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result


@pytest.mark.parametrize(
    "test_case",
    [
        RenderNodeSourceWatermarkSqlTestCase(
            description="inserts one row per node run with encoded payload",
            expected_contains=(
                f"INSERT INTO analytics.{NODE_SOURCE_WATERMARK_TABLE_NAME}",
                "node_type, node_name, target_database, target_schema, target_name",
                "watermarks_json_b64",
            ),
        )
    ],
    ids=["inserts one row per node run with encoded payload"],
)
def test_given_watermark_record_when_rendering_insert_sql_then_inserts_payload_row(
    test_case: RenderNodeSourceWatermarkSqlTestCase,
) -> None:
    record: NodeSourceWatermarkRecord = NodeSourceWatermarkRecord(
        node_type="model",
        node_name="fact_orders",
        target_database=None,
        target_schema="analytics",
        target_name="fact_orders",
        run_id="run-1",
        node_version_hash="version-1",
        payload=NodeSourceWatermarkPayload(
            version=1,
            complete=True,
            sources=(
                SourceWatermarkEntry(
                    source_name="hkjc.events",
                    target_database=None,
                    target_schema="raw",
                    target_name="events",
                    strategy="adapter_metadata",
                    value_kind="timestamp",
                    data_version="2026-06-29T15:37:00",
                    data_version_hash="abc123",
                    observed_at=datetime(2026, 6, 29, 15, 38),
                    watermark_kind="direct",
                ),
            ),
        ),
        created_at=datetime(2026, 6, 29, 15, 39),
    )

    result: str = render_insert_node_source_watermark_records_sql(
        database=None,
        schema="analytics",
        records=(record,),
        render_qualified_name=ADAPTER.render_qualified_name,
    )

    fragment: str
    for fragment in test_case.expected_contains:
        assert fragment in result
    assert encode_watermark_payload(record.payload) in result
