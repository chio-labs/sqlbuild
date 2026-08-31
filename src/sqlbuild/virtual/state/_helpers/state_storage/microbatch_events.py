"""DuckDB storage helpers for virtual microbatch events."""

from __future__ import annotations

from typing import Any

from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import (
    MICROBATCH_COLUMNS,
    MICROBATCH_GENERATION_WILDCARD,
    VIRTUAL_MICROBATCH_SCOPE_KIND,
)
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope, MicrobatchWriteResult


def append_duckdb_microbatch_event(
    *, connection: Any, qualified_table: str, event: MicrobatchEvent
) -> None:
    """Append one idempotent logical event to DuckDB state."""

    placeholders: str = ", ".join("?" for _ in MICROBATCH_COLUMNS)
    connection.execute(
        f"INSERT INTO {qualified_table} ({', '.join(MICROBATCH_COLUMNS)}) "
        f"SELECT {placeholders} WHERE NOT EXISTS "
        f"(SELECT 1 FROM {qualified_table} WHERE event_id = ?)",
        [*MicrobatchEventCodec.values(event), event.event_id],
    )


def append_duckdb_microbatch_events(
    *, connection: Any, qualified_table: str, events: tuple[MicrobatchEvent, ...]
) -> MicrobatchWriteResult:
    """Append idempotent logical events to DuckDB state in one statement."""

    if not events:
        return MicrobatchWriteResult(total=0, inserted=0, already_existing=0)
    id_placeholders: str = ", ".join("?" for _ in events)
    existing_rows: list[tuple[str]] = connection.execute(
        f"SELECT event_id FROM {qualified_table} WHERE event_id IN ({id_placeholders})",
        [event.event_id for event in events],
    ).fetchall()
    existing_ids: frozenset[str] = frozenset(row[0] for row in existing_rows)
    missing: tuple[MicrobatchEvent, ...] = tuple(
        event for event in events if event.event_id not in existing_ids
    )
    if missing:
        row_placeholders: str = "(" + ", ".join("?" for _ in MICROBATCH_COLUMNS) + ")"
        values_sql: str = ", ".join(row_placeholders for _ in missing)
        params: list[object | None] = []
        for event in missing:
            params.extend(MicrobatchEventCodec.values(event))
        columns: str = ", ".join(MICROBATCH_COLUMNS)
        connection.execute(
            f"INSERT INTO {qualified_table} ({columns}) SELECT {columns} FROM "
            f"(VALUES {values_sql}) AS incoming ({columns}) WHERE NOT EXISTS "
            f"(SELECT 1 FROM {qualified_table} existing "
            "WHERE existing.event_id = incoming.event_id)",
            params,
        )
    return MicrobatchWriteResult(
        total=len(events), inserted=len(missing), already_existing=len(events) - len(missing)
    )


def read_duckdb_microbatch_scope_history(
    *, connection: Any, qualified_table: str, scope: MicrobatchScope
) -> tuple[MicrobatchEvent, ...]:
    """Read ordered history for one DuckDB physical scope."""

    generation_sql: str = (
        ""
        if scope.physical_generation_id == MICROBATCH_GENERATION_WILDCARD
        else "AND physical_generation_id = ? "
    )
    params: list[object] = [scope.scope_kind, scope.scope_key]
    if scope.physical_generation_id != MICROBATCH_GENERATION_WILDCARD:
        params.append(scope.physical_generation_id)
    rows: list[tuple[Any, ...]] = connection.execute(
        f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM {qualified_table} "
        f"WHERE scope_kind = ? AND scope_key = ? {generation_sql}"
        "ORDER BY created_at, event_id",
        params,
    ).fetchall()
    return tuple(MicrobatchEventCodec.from_row(tuple(row)) for row in rows)


def read_duckdb_microbatch_retention_history(
    *, connection: Any, qualified_table: str
) -> tuple[MicrobatchEvent, ...]:
    """Read ordered virtual-scope history from DuckDB state."""

    rows: list[tuple[Any, ...]] = connection.execute(
        f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM {qualified_table} "
        "WHERE scope_kind = ? ORDER BY created_at, event_id",
        [VIRTUAL_MICROBATCH_SCOPE_KIND],
    ).fetchall()
    return tuple(MicrobatchEventCodec.from_row(tuple(row)) for row in rows)


def read_duckdb_microbatch_model_history(
    *, connection: Any, qualified_table: str, scope: MicrobatchScope
) -> tuple[MicrobatchEvent, ...]:
    """Read ordered history for one model in one warehouse realm."""

    warehouse_realm: str = scope.physical_generation_id.partition(":")[0]
    rows: list[tuple[Any, ...]] = connection.execute(
        f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM {qualified_table} "
        "WHERE scope_kind = ? AND model_name = ? AND physical_generation_id LIKE ? "
        "ORDER BY created_at, event_id",
        [scope.scope_kind, scope.model_name, f"{warehouse_realm}:%"],
    ).fetchall()
    return tuple(MicrobatchEventCodec.from_row(tuple(row)) for row in rows)
