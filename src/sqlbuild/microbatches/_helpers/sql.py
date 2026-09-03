"""Internal portable SQL for direct-mode microbatch history."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.microbatches.classes.event_codec import MicrobatchEventCodec
from sqlbuild.microbatches.constants import (
    MICROBATCH_COLUMNS,
    MICROBATCH_GENERATION_WILDCARD,
    MICROBATCH_INTEGER_COLUMNS,
    MICROBATCH_TABLE_NAME,
)
from sqlbuild.microbatches.exceptions import MicrobatchStateError
from sqlbuild.microbatches.models import MicrobatchEvent, MicrobatchScope


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> str:
    table: str = _qualified_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    text_type: str = render_framework_type(FrameworkType.STRING)
    timestamp_type: str = render_framework_type(FrameworkType.TIMESTAMP)
    definitions: list[str] = []
    for column in MICROBATCH_COLUMNS:
        if column.endswith("_at"):
            column_type: str = timestamp_type
        elif column in MICROBATCH_INTEGER_COLUMNS:
            column_type = "BIGINT"
        else:
            column_type = text_type
        definitions.append(f"{column} {column_type}")
    return f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(definitions)})"


def build_insert_sql(
    *, event: MicrobatchEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = _qualified_table(
        database=event.scope.target_database,
        schema=_required_schema(event.scope),
        render_qualified_name=render_qualified_name,
    )
    values: tuple[object | None, ...] = MicrobatchEventCodec.values(event)
    literals: str = ", ".join(
        _column_literal(column=column, value=value)
        for column, value in zip(MICROBATCH_COLUMNS, values, strict=True)
    )
    return (
        f"INSERT INTO {table} ({', '.join(MICROBATCH_COLUMNS)}) SELECT "
        f"{literals} "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} "
        f"WHERE event_id = {_literal(event.event_id)})"
    )


def build_insert_many_sql(
    *, events: tuple[MicrobatchEvent, ...], render_qualified_name: Callable[..., str | None]
) -> str:
    """Build one guarded set-based insert for events in the same state table."""

    if not events:
        raise MicrobatchStateError("bulk microbatch event insert requires at least one event")
    first: MicrobatchEvent = events[0]
    table: str = _qualified_table(
        database=first.scope.target_database,
        schema=_required_schema(first.scope),
        render_qualified_name=render_qualified_name,
    )
    selections: list[str] = []
    for index, event in enumerate(events):
        values: tuple[object | None, ...] = MicrobatchEventCodec.values(event)
        aliases: str = (
            ""
            if index > 0
            else " "
            + ", ".join(
                f"{_column_literal(column=column, value=value)} AS {column}"
                for column, value in zip(MICROBATCH_COLUMNS, values, strict=True)
            )
        )
        selections.append(
            "SELECT "
            + ", ".join(
                _column_literal(column=column, value=value)
                for column, value in zip(MICROBATCH_COLUMNS, values, strict=True)
            )
            if index > 0
            else f"SELECT{aliases}"
        )
    columns: str = ", ".join(MICROBATCH_COLUMNS)
    return (
        f"INSERT INTO {table} ({columns}) SELECT {columns} FROM "
        f"({' UNION ALL '.join(selections)}) AS incoming "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} AS existing "
        "WHERE existing.event_id = incoming.event_id)"
    )


def build_existing_event_ids_sql(
    *, events: tuple[MicrobatchEvent, ...], render_qualified_name: Callable[..., str | None]
) -> str:
    """Build one lookup for event IDs already present before a bulk insert."""

    if not events:
        raise MicrobatchStateError("microbatch event lookup requires at least one event")
    first: MicrobatchEvent = events[0]
    table: str = _qualified_table(
        database=first.scope.target_database,
        schema=_required_schema(first.scope),
        render_qualified_name=render_qualified_name,
    )
    return (
        f"SELECT event_id FROM {table} WHERE event_id IN "
        f"({', '.join(_literal(event.event_id) for event in events)})"
    )


def build_read_scope_sql(
    *, scope: MicrobatchScope, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = _qualified_table(
        database=scope.target_database,
        schema=_required_schema(scope),
        render_qualified_name=render_qualified_name,
    )
    generation_predicate: str = (
        ""
        if scope.physical_generation_id == MICROBATCH_GENERATION_WILDCARD
        else f"AND physical_generation_id = {_literal(scope.physical_generation_id)} "
    )
    return (
        f"SELECT {', '.join(MICROBATCH_COLUMNS)} FROM {table} "
        f"WHERE scope_kind = {_literal(scope.scope_kind)} "
        f"AND scope_key = {_literal(scope.scope_key)} "
        f"{generation_predicate}"
        "ORDER BY created_at, event_id"
    )


def _qualified_table(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str | None = render_qualified_name(
        database=database, schema=schema, name=MICROBATCH_TABLE_NAME
    )
    if table is None:
        raise MicrobatchStateError("microbatch history requires a target schema")
    return table


def _required_schema(scope: MicrobatchScope) -> str:
    if scope.target_schema is None:
        raise MicrobatchStateError("microbatch history requires a target schema")
    return scope.target_schema


def _literal(value: object | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    normalized: str = value.isoformat() if isinstance(value, date | datetime) else str(value)
    return "'" + normalized.replace("'", "''") + "'"


def _column_literal(*, column: str, value: object | None) -> str:
    literal: str = _literal(value)
    if column in MICROBATCH_INTEGER_COLUMNS:
        return f"CAST({literal} AS BIGINT)"
    if column.endswith("_at"):
        return f"CAST({literal} AS TIMESTAMP)"
    return literal
