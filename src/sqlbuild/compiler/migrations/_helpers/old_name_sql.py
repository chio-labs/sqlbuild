"""Portable SQL for append-only old-name view facts."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from typing import Any

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapter.state_sql.main.render_state_table_create_sql import (
    render_state_table_create_sql,
)
from sqlbuild.compiler.migrations._helpers.sql import (
    decode_event_timestamp,
    optional_text,
    render_event_exists_sql,
    render_event_insert_sql,
)
from sqlbuild.compiler.migrations.constants import (
    OLD_NAME_VIEW_COLUMN_TYPES,
    OLD_NAME_VIEW_COLUMNS,
    OLD_NAME_VIEW_TABLE_NAME,
)
from sqlbuild.compiler.migrations.exceptions import MigrationStateError
from sqlbuild.compiler.migrations.models import MigrationRelation, OldNameViewEvent
from sqlbuild.compiler.migrations.types import OldNameViewDropReason, OldNameViewEventType


def qualified_old_name_view_table(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    table: str | None = render_qualified_name(
        database=database, schema=schema, name=OLD_NAME_VIEW_TABLE_NAME
    )
    if table is None:
        raise MigrationStateError("old-name view state requires a target schema")
    return table


def build_old_name_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool,
) -> str:
    return render_state_table_create_sql(
        qualified_name=qualified_old_name_view_table(
            database=database, schema=schema, render_qualified_name=render_qualified_name
        ),
        columns=OLD_NAME_VIEW_COLUMNS,
        column_types=OLD_NAME_VIEW_COLUMN_TYPES,
        required_columns=frozenset(),
        render_framework_type=render_framework_type,
        transient=transient,
    )


def build_old_name_existing_event_sql(
    *, event: OldNameViewEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    return render_event_exists_sql(
        table=_event_table(event=event, render_qualified_name=render_qualified_name),
        event_id=event.event_id,
    )


def build_old_name_insert_sql(
    *, event: OldNameViewEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    return render_event_insert_sql(
        table=_event_table(event=event, render_qualified_name=render_qualified_name),
        columns=OLD_NAME_VIEW_COLUMNS,
        column_types=OLD_NAME_VIEW_COLUMN_TYPES,
        values=(
            event.event_id,
            event.target_name,
            event.event_type.value,
            event.migration_event_id,
            event.destination_model,
            event.old.database,
            event.old.schema,
            event.old.name,
            event.new.database,
            event.new.schema,
            event.new.name,
            event.view_retention,
            event.archive_name,
            _encode_aliases(event.column_aliases) if event.column_aliases else None,
            None if event.grants_copied is None else json.dumps(list(event.grants_copied)),
            event.view_sql,
            event.expires_at,
            None if event.drop_reason is None else event.drop_reason.value,
            event.run_id,
            event.created_at,
        ),
    )


def readable_old_name_columns(stored_columns: Iterable[str]) -> tuple[str, ...]:
    """Return the known columns a stored table has; columns added later may be absent."""

    stored: frozenset[str] = frozenset(column.lower() for column in stored_columns)
    return tuple(column for column in OLD_NAME_VIEW_COLUMNS if column in stored)


def build_old_name_read_sql(
    *,
    database: str | None,
    schema: str,
    columns: tuple[str, ...],
    render_qualified_name: Callable[..., str | None],
) -> str:
    table: str = qualified_old_name_view_table(
        database=database, schema=schema, render_qualified_name=render_qualified_name
    )
    return f"SELECT {', '.join(columns)} FROM {table} ORDER BY created_at, event_id"


def decode_old_name_event_row(
    *, row: tuple[Any, ...], columns: tuple[str, ...] = OLD_NAME_VIEW_COLUMNS
) -> OldNameViewEvent | None:
    """Decode one row of ``columns``, reading absent ones as NULL; skip unknown event types."""

    values: dict[str, Any] = dict(zip(columns, row, strict=False))
    try:
        event_type: OldNameViewEventType = OldNameViewEventType(str(values.get("event_type")))
    except ValueError:
        return None
    raw_reason: str | None = optional_text(values.get("drop_reason"))
    raw_expires: object | None = values.get("expires_at")
    return OldNameViewEvent(
        event_id=str(values["event_id"]),
        target_name=optional_text(values.get("target_name")),
        event_type=event_type,
        migration_event_id=str(values["migration_event_id"]),
        destination_model=str(values["destination_model"]),
        old=MigrationRelation(
            database=optional_text(values.get("old_database")),
            schema=optional_text(values.get("old_schema")),
            name=str(values["old_name"]),
        ),
        new=MigrationRelation(
            database=optional_text(values.get("new_database")),
            schema=optional_text(values.get("new_schema")),
            name=str(values["new_name"]),
        ),
        run_id=str(values["run_id"]),
        created_at=decode_event_timestamp(values["created_at"]),
        view_retention=optional_text(values.get("view_retention")),
        archive_name=optional_text(values.get("archive_name")),
        column_aliases=_decode_aliases(optional_text(values.get("column_aliases"))),
        expires_at=None if raw_expires is None else decode_event_timestamp(raw_expires),
        drop_reason=_decode_reason(raw_reason),
        grants_copied=_decode_grants(optional_text(values.get("grants_copied"))),
        view_sql=optional_text(values.get("view_sql")),
    )


def _decode_reason(raw: str | None) -> OldNameViewDropReason | None:
    if raw is None:
        return None
    try:
        return OldNameViewDropReason(raw)
    except ValueError:
        return None


def _decode_grants(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return tuple(str(statement) for statement in payload)


def _encode_aliases(aliases: tuple[tuple[str, str], ...]) -> str:
    return json.dumps(dict(aliases), sort_keys=True, separators=(",", ":"))


def _decode_aliases(raw: str | None) -> tuple[tuple[str, str], ...]:
    if not raw:
        return ()
    try:
        payload: object = json.loads(raw)
    except json.JSONDecodeError:
        return ()
    if not isinstance(payload, dict):
        return ()
    return tuple(sorted((str(old), str(new)) for old, new in payload.items()))


def _event_table(
    *, event: OldNameViewEvent, render_qualified_name: Callable[..., str | None]
) -> str:
    if event.new.schema is None:
        raise MigrationStateError("old-name view facts require a destination schema")
    return qualified_old_name_view_table(
        database=event.new.database,
        schema=event.new.schema,
        render_qualified_name=render_qualified_name,
    )
