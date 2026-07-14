"""Adapter-owned renderers for node source watermark state."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.exceptions import AdapterUserError
from sqlbuild.adapter.types import FrameworkType
from sqlbuild.compiler.node_source_watermarks.constants import (
    COLUMN_CREATED_AT,
    COLUMN_NODE_NAME,
    COLUMN_NODE_TYPE,
    COLUMN_NODE_VERSION_HASH,
    COLUMN_RUN_ID,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_NAME,
    COLUMN_TARGET_SCHEMA,
    COLUMN_WATERMARKS_JSON_B64,
    NODE_SOURCE_WATERMARK_TABLE_NAME,
)
from sqlbuild.compiler.node_source_watermarks.main.encode_payload import (
    encode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkRecord


def render_create_node_source_watermark_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    """Render DDL that creates the node source watermark table."""

    table_name: str = _watermark_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    string_type: str = render_framework_type(FrameworkType.STRING)
    timestamp_type: str = render_framework_type(FrameworkType.TIMESTAMP)
    table_kind: str = "TRANSIENT TABLE" if transient else "TABLE"
    return (
        f"CREATE {table_kind} IF NOT EXISTS {table_name} ("
        f"{COLUMN_NODE_TYPE} {string_type} NOT NULL, "
        f"{COLUMN_NODE_NAME} {string_type} NOT NULL, "
        f"{COLUMN_TARGET_DATABASE} {string_type}, "
        f"{COLUMN_TARGET_SCHEMA} {string_type}, "
        f"{COLUMN_TARGET_NAME} {string_type}, "
        f"{COLUMN_RUN_ID} {string_type} NOT NULL, "
        f"{COLUMN_NODE_VERSION_HASH} {string_type} NOT NULL, "
        f"{COLUMN_WATERMARKS_JSON_B64} {string_type} NOT NULL, "
        f"{COLUMN_CREATED_AT} {timestamp_type} NOT NULL"
        f")"
    )


def render_read_latest_node_source_watermarks_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Render SQL that reads latest node source watermark rows per identity."""

    table_name: str = _watermark_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    selected_columns: str = _select_columns()
    return (
        f"SELECT {selected_columns} "
        f"FROM ("
        f"SELECT {selected_columns}, "
        f"ROW_NUMBER() OVER ("
        f"PARTITION BY {COLUMN_NODE_TYPE}, {COLUMN_NODE_NAME} "
        f"ORDER BY {COLUMN_CREATED_AT} DESC, {COLUMN_RUN_ID} DESC"
        f") AS __sqlbuild_latest_rank "
        f"FROM {table_name}"
        f") AS __sqlbuild_latest_node_source_watermarks "
        f"WHERE __sqlbuild_latest_rank = 1"
    )


def render_insert_node_source_watermark_records_sql(
    *,
    database: str | None,
    schema: str,
    records: tuple[NodeSourceWatermarkRecord, ...],
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Render DML that appends node source watermark records."""

    table_name: str = _watermark_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    values_sql: str = ", ".join(_record_values_sql(record) for record in records)
    return (
        f"INSERT INTO {table_name} ("
        f"{COLUMN_NODE_TYPE}, "
        f"{COLUMN_NODE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_NODE_VERSION_HASH}, "
        f"{COLUMN_WATERMARKS_JSON_B64}, "
        f"{COLUMN_CREATED_AT}"
        f") VALUES {values_sql}"
    )


def _watermark_table_name(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    table_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=NODE_SOURCE_WATERMARK_TABLE_NAME,
    )
    if table_name is None:
        raise AdapterUserError(message="node source watermark table requires a target schema")
    return table_name


def _select_columns() -> str:
    return (
        f"{COLUMN_NODE_TYPE}, "
        f"{COLUMN_NODE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_NODE_VERSION_HASH}, "
        f"{COLUMN_WATERMARKS_JSON_B64}, "
        f"{COLUMN_CREATED_AT}"
    )


def _record_values_sql(record: NodeSourceWatermarkRecord) -> str:
    return (
        "("
        f"{_quote_sql_string(record.node_type)}, "
        f"{_quote_sql_string(record.node_name)}, "
        f"{_optional_string(record.target_database)}, "
        f"{_optional_string(record.target_schema)}, "
        f"{_optional_string(record.target_name)}, "
        f"{_quote_sql_string(record.run_id)}, "
        f"{_quote_sql_string(record.node_version_hash)}, "
        f"{_quote_sql_string(encode_watermark_payload(record.payload))}, "
        f"{_quote_sql_string(record.created_at.isoformat())}"
        ")"
    )


def _optional_string(value: str | None) -> str:
    if value is None:
        return "NULL"
    return _quote_sql_string(value)


def _quote_sql_string(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
