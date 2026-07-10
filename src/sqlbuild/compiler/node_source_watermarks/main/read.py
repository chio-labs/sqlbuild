"""Standard node source watermark read operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.shared.types import AdapterExecute
from sqlbuild.compiler.node_source_watermarks.constants import (
    NODE_SOURCE_WATERMARK_TABLE_NAME,
)
from sqlbuild.compiler.node_source_watermarks.exceptions import (
    NodeSourceWatermarkInputError,
)
from sqlbuild.compiler.node_source_watermarks.main.decode_payload import (
    decode_watermark_payload,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkSet,
)


def read_latest_node_source_watermarks(
    *,
    connection: Any,
    execute: AdapterExecute[Any, Any],
    table_exists: bool,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_read_latest_sql: Callable[..., str],
) -> NodeSourceWatermarkSet:
    """Read latest node source watermark rows from adapter-rendered SQL."""

    if not table_exists:
        return NodeSourceWatermarkSet(schema=schema)
    qualified_name: str = _qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    try:
        result: Any = execute(
            connection,
            sql=render_read_latest_sql(database=database, schema=schema),
        )
    except Exception as error:
        raise NodeSourceWatermarkInputError(
            f"Unable to read node source watermarks from {qualified_name}. Delete or rebuild "
            "the SQLBuild node source watermark table to regenerate state."
        ) from error
    rows: list[tuple[Any, ...]] = result.fetchall()
    records: dict[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord] = {}
    row: tuple[Any, ...]
    for row in rows:
        record: NodeSourceWatermarkRecord = _row_to_record(row, qualified_name=qualified_name)
        records[record.identity] = record
    return NodeSourceWatermarkSet(schema=schema, records=records)


def _qualified_table_name(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=NODE_SOURCE_WATERMARK_TABLE_NAME,
    )
    if qualified_name is None:
        raise NodeSourceWatermarkInputError("node source watermark table requires a target schema")
    return qualified_name


def _row_to_record(row: tuple[Any, ...], *, qualified_name: str) -> NodeSourceWatermarkRecord:
    raw_target_database: Any = row[2]
    raw_target_schema: Any = row[3]
    raw_target_name: Any = row[4]
    raw_created_at: Any = row[8]
    created_at: datetime = (
        raw_created_at
        if isinstance(raw_created_at, datetime)
        else datetime.fromisoformat(str(raw_created_at))
    )
    return NodeSourceWatermarkRecord(
        node_type=str(row[0]),
        node_name=str(row[1]),
        target_database=str(raw_target_database) if raw_target_database is not None else None,
        target_schema=str(raw_target_schema) if raw_target_schema is not None else None,
        target_name=str(raw_target_name) if raw_target_name is not None else None,
        run_id=str(row[5]),
        node_version_hash=str(row[6]),
        payload=decode_watermark_payload(str(row[7]), qualified_name=qualified_name),
        created_at=created_at,
    )
