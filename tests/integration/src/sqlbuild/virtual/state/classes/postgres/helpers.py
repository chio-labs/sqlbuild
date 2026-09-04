from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import MICROBATCH_COLUMNS
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
from sqlbuild.microbatches.types import (
    MicrobatchCompletionType,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
)
from sqlbuild.virtual.state.constants import MICROBATCH_EVENT_TABLE


def build_unique_schema_name(*, prefix: str) -> str:
    suffix: str = uuid.uuid4().hex[:10]
    return f"{prefix}_{suffix}"


def fetch_all(connection: Any, sql: str) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return [tuple(row) for row in cursor.fetchall()]


def qualified_name(*, schema: str, table: str) -> str:
    return f"{quote_identifier(schema)}.{quote_identifier(table)}"


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def postgres_microbatch_scope() -> MicrobatchScope:
    """Build the shared virtual scope used by Postgres history tests."""

    return MicrobatchScope(
        scope_kind="virtual_physical",
        scope_key="postgres:state:orders:F2:analytics.orders__F2",
        model_name="orders",
        target_database="warehouse",
        target_schema="analytics",
        target_name="orders__F2",
        physical_generation_id="F2:analytics.orders__F2",
        virtual_environment_name="dev",
        virtual_model_version_hash="F2",
    )


def postgres_microbatch_event(*, scope: MicrobatchScope, event_id: str) -> MicrobatchEvent:
    """Build one active Postgres microbatch event."""

    return MicrobatchEvent(
        event_id=event_id,
        record_type=MicrobatchRecordType.PARTITION_COMPLETION,
        scope=scope,
        origin_run_id="run-1",
        execution_run_id="run-1",
        run_type=MicrobatchRunType.NORMAL,
        completion_type=MicrobatchCompletionType.INITIAL,
        run_start="0",
        run_end="1",
        partition_start="0",
        partition_end="1",
        batch_size="1",
        cursor_column="batch_id",
        cursor_type="integer",
        model_version_hash="F2",
        definition_hash="definition",
        fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
        rows_affected=0,
        created_at=datetime(2026, 1, 1),
    )


def insert_raw_postgres_microbatch_record(
    *,
    connection: Any,
    schema: str,
    event: MicrobatchEvent,
    event_id: str,
    record_type: str,
) -> None:
    """Insert one persisted Postgres event with a raw record type."""

    values: list[object | None] = list(MicrobatchEventCodec.values(event))
    values[0] = event_id
    values[1] = record_type
    placeholders: str = ", ".join("%s" for _ in values)
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {qualified_name(schema=schema, table=MICROBATCH_EVENT_TABLE)} "
            f"({', '.join(MICROBATCH_COLUMNS)}) VALUES ({placeholders})",
            values,
        )
