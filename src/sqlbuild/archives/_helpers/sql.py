"""Portable direct-mode archive event SQL."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.archives.classes.event_codec import ArchiveEventCodec
from sqlbuild.archives.constants import (
    ARCHIVE_EVENT_COLUMNS,
    ARCHIVE_EVENT_TABLE_NAME,
    ARCHIVE_INTEGER_COLUMNS,
)
from sqlbuild.archives.exceptions import ArchiveStateError
from sqlbuild.archives.models import ArchiveEvent


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
    for column in ARCHIVE_EVENT_COLUMNS:
        if column.endswith("_at"):
            column_type: str = timestamp_type
        elif column in ARCHIVE_INTEGER_COLUMNS:
            column_type = "BIGINT"
        else:
            column_type = text_type
        definitions.append(f"{column} {column_type}")
    return f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(definitions)})"


def build_insert_sql(
    *, event: ArchiveEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str = _qualified_table(
        database=event.target_database,
        schema=event.target_schema,
        render_qualified_name=render_qualified_name,
    )
    values: tuple[object | None, ...] = ArchiveEventCodec.values(event)
    return (
        f"INSERT INTO {table} ({', '.join(ARCHIVE_EVENT_COLUMNS)}) SELECT "
        f"{', '.join(_literal(value) for value in values)} "
        f"WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE event_id = {_literal(event.event_id)})"
    )


def build_read_target_sql(
    *,
    database: str | None,
    schema: str,
    target_name: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    table: str = _qualified_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    database_predicate: str = (
        "target_database IS NULL" if database is None else f"target_database = {_literal(database)}"
    )
    return (
        f"SELECT {', '.join(ARCHIVE_EVENT_COLUMNS)} FROM {table} "
        f"WHERE {database_predicate} AND target_schema = {_literal(schema)} "
        f"AND target_name = {_literal(target_name)} ORDER BY created_at, event_id"
    )


def build_read_schema_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    table: str = _qualified_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    return f"SELECT {', '.join(ARCHIVE_EVENT_COLUMNS)} FROM {table} ORDER BY created_at, event_id"


def _qualified_table(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str | None = render_qualified_name(
        database=database, schema=schema, name=ARCHIVE_EVENT_TABLE_NAME
    )
    if table is None:
        raise ArchiveStateError("archive history requires a target schema")
    return table


def _literal(value: object | None) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    normalized: str = value.isoformat() if isinstance(value, date | datetime) else str(value)
    return "'" + normalized.replace("'", "''") + "'"
