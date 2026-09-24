"""Portable SQL builders for append-only janitor audit events."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.types import FrameworkType
from sqlbuild.adapter.state_sql.main.render_state_table_create_sql import (
    render_state_table_create_sql,
)
from sqlbuild.errors.contracts.exceptions import ExecutorInputError
from sqlbuild.executor.janitor_events.constants import (
    COLUMN_ARCHIVE_NAME,
    COLUMN_ARCHIVE_QUALIFIED_NAME,
    COLUMN_ARCHIVED_AT,
    COLUMN_EVENT_ID,
    COLUMN_EVENT_TYPE,
    COLUMN_OCCURRED_AT,
    COLUMN_ORIGINAL_NAME,
    COLUMN_ORIGINAL_QUALIFIED_NAME,
    COLUMN_RELATION_DATABASE,
    COLUMN_RELATION_SCHEMA,
    COLUMN_RELATION_TYPE,
    COLUMN_RUN_ID,
    COLUMN_SCHEMA_VERSION,
    JANITOR_EVENT_COLUMN_TYPES,
    JANITOR_EVENT_COLUMNS,
    JANITOR_EVENT_REQUIRED_COLUMNS,
    JANITOR_EVENTS_TABLE_NAME,
)
from sqlbuild.executor.janitor_events.models import JanitorEventRecord
from sqlbuild.sql_values.main.render_state_literal import render_state_sql_literal


def build_qualified_table_name(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    qualified_name: str | None = render_qualified_name(
        database=database, schema=schema, name=JANITOR_EVENTS_TABLE_NAME
    )
    if qualified_name is None:
        raise ExecutorInputError("janitor event table requires a target schema")
    return qualified_name


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
    transient: bool = False,
) -> str:
    return render_state_table_create_sql(
        qualified_name=build_qualified_table_name(
            database=database, schema=schema, render_qualified_name=render_qualified_name
        ),
        columns=JANITOR_EVENT_COLUMNS,
        column_types=JANITOR_EVENT_COLUMN_TYPES,
        required_columns=JANITOR_EVENT_REQUIRED_COLUMNS,
        render_framework_type=render_framework_type,
        transient=transient,
    )


def build_existing_event_sql(
    *,
    record: JanitorEventRecord,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str = build_qualified_table_name(
        database=record.relation_database,
        schema=record.relation_schema,
        render_qualified_name=render_qualified_name,
    )
    event_id: str = _column_literal(column=COLUMN_EVENT_ID, value=record.event_id)
    return f"SELECT {COLUMN_EVENT_ID} FROM {qualified_name} WHERE {COLUMN_EVENT_ID} = {event_id}"


def build_insert_sql(
    *,
    record: JanitorEventRecord,
    render_qualified_name: Callable[..., str | None],
) -> str:
    qualified_name: str = build_qualified_table_name(
        database=record.relation_database,
        schema=record.relation_schema,
        render_qualified_name=render_qualified_name,
    )
    values: dict[str, object | None] = {
        COLUMN_EVENT_ID: record.event_id,
        COLUMN_SCHEMA_VERSION: record.schema_version,
        COLUMN_EVENT_TYPE: record.event_type.value,
        COLUMN_OCCURRED_AT: record.occurred_at,
        COLUMN_RUN_ID: record.run_id,
        COLUMN_RELATION_DATABASE: record.relation_database,
        COLUMN_RELATION_SCHEMA: record.relation_schema,
        COLUMN_RELATION_TYPE: record.relation_type,
        COLUMN_ORIGINAL_NAME: record.original_name,
        COLUMN_ORIGINAL_QUALIFIED_NAME: record.original_qualified_name,
        COLUMN_ARCHIVE_NAME: record.archive_name,
        COLUMN_ARCHIVE_QUALIFIED_NAME: record.archive_qualified_name,
        COLUMN_ARCHIVED_AT: record.archived_at,
    }
    literals: str = ", ".join(
        _column_literal(column=column, value=values[column]) for column in JANITOR_EVENT_COLUMNS
    )
    return f"INSERT INTO {qualified_name} ({', '.join(JANITOR_EVENT_COLUMNS)}) VALUES ({literals})"


def _column_literal(*, column: str, value: object | None) -> str:
    return render_state_sql_literal(value=value, declared_type=JANITOR_EVENT_COLUMN_TYPES[column])
