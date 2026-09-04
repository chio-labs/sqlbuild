"""Helpers for direct microbatch store integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import MICROBATCH_COLUMNS
from sqlbuild.microbatches.main.deterministic_event_id import (
    deterministic_microbatch_event_id,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope
from sqlbuild.microbatches.types import (
    MicrobatchCompletionType,
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    MicrobatchRunType,
)


def build_events(*, count: int, start_at: int = 0) -> tuple[MicrobatchEvent, ...]:
    """Build deterministic direct-mode partition completion events."""

    scope: MicrobatchScope = MicrobatchScope(
        scope_kind="direct_logical",
        scope_key="duckdb:main.orders",
        model_name="orders",
        target_database=None,
        target_schema="main",
        target_name="orders",
        physical_generation_id="generation-1",
    )
    events: list[MicrobatchEvent] = []
    for index in range(start_at, start_at + count):
        partition_start: str = str(index)
        partition_end: str = str(index + 1)
        event_id: str = deterministic_microbatch_event_id(
            scope=scope,
            record_type=MicrobatchRecordType.PARTITION_COMPLETION,
            partition_start=partition_start,
            partition_end=partition_end,
            completion_reason=MicrobatchCompletionType.INITIAL.value,
        )
        events.append(
            MicrobatchEvent(
                event_id=event_id,
                record_type=MicrobatchRecordType.PARTITION_COMPLETION,
                scope=scope,
                origin_run_id="run-1",
                execution_run_id="run-1",
                run_type=MicrobatchRunType.NORMAL,
                run_start="0",
                run_end=str(start_at + count),
                batch_size="1",
                cursor_column="batch_id",
                cursor_type="integer",
                model_version_hash="F2",
                definition_hash="definition",
                fingerprint_status=MicrobatchFingerprintStatus.KNOWN,
                completion_type=MicrobatchCompletionType.INITIAL,
                partition_start=partition_start,
                partition_end=partition_end,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    return tuple(events)


def insert_raw_event_record_type(
    *, connection: Any, event: MicrobatchEvent, record_type: str
) -> None:
    """Insert a persisted event using a raw record type string."""

    values: list[object | None] = list(MicrobatchEventCodec.values(event))
    values[1] = record_type
    placeholders: str = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO main._sqlbuild_microbatches ({', '.join(MICROBATCH_COLUMNS)}) "
        f"VALUES ({placeholders})",
        values,
    )
