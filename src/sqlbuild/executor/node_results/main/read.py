"""Runtime node result read operations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.executor.node_results.constants import NODE_RESULTS_TABLE_NAME
from sqlbuild.executor.node_results.helpers.serialization import decode_json_b64
from sqlbuild.executor.node_results.helpers.sql import build_read_history_sql
from sqlbuild.executor.node_results.models import NodeResultEnvelope


def read_node_results(
    *,
    connection: Any,
    execute: Any,
    relation_exists: Callable[..., bool],
    database: str | None,
    schema: str,
    node_type: str,
    node_name: str,
    target_database: str | None,
    target_schema: str | None,
    target_name: str | None,
    statuses: tuple[str, ...] | None,
    run_id: str | None,
    limit: int,
    render_qualified_name: Callable[..., str | None],
) -> tuple[NodeResultEnvelope, ...]:
    """Read persisted node results for one runtime node identity."""

    if limit < 1:
        return ()
    if not relation_exists(
        connection,
        database=database,
        schema=schema,
        name=NODE_RESULTS_TABLE_NAME,
    ):
        return ()
    read_sql: str = build_read_history_sql(
        database=database,
        schema=schema,
        node_type=node_type,
        node_name=node_name,
        target_database=target_database,
        target_schema=target_schema,
        target_name=target_name,
        statuses=statuses,
        run_id=run_id,
        render_qualified_name=render_qualified_name,
    )
    result: Any = execute(connection, read_sql)
    rows: list[tuple[Any, ...]] = result.fetchall()
    return tuple(_row_to_envelope(row) for row in rows[:limit])


def _row_to_envelope(row: tuple[Any, ...]) -> NodeResultEnvelope:
    node_name: str = str(row[1])
    raw_ts: Any = row[11]
    ts: datetime = raw_ts if isinstance(raw_ts, datetime) else datetime.fromisoformat(str(raw_ts))
    metadata: object = decode_json_b64(str(row[8]), label="metadata", node_name=node_name)
    normalized_metadata: dict[str, object] = (
        {str(key): value for key, value in metadata.items()} if isinstance(metadata, dict) else {}
    )
    return NodeResultEnvelope(
        node_type=str(row[0]),
        node_name=node_name,
        run_id=str(row[5]),
        status=str(row[6]),
        payload=decode_json_b64(str(row[7]), label="payload", node_name=node_name),
        metadata=normalized_metadata,
        error_message=str(row[9]) if row[9] is not None else None,
        materialized=_parse_materialized(row[10]),
        ts=ts,
    )


def _parse_materialized(value: object) -> bool | None:
    if value is None:
        return None
    return str(value).lower() == "true"
