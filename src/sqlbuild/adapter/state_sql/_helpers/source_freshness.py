"""Adapter-owned renderers for source freshness state."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.compiler.source_freshness.constants import (
    COLUMN_DATA_VERSION,
    COLUMN_DATA_VERSION_HASH,
    COLUMN_OBSERVED_AT,
    COLUMN_RUN_ID,
    COLUMN_SOURCE_NAME,
    COLUMN_STRATEGY,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_NAME,
    COLUMN_TARGET_SCHEMA,
    COLUMN_VALUE_KIND,
    SOURCE_FRESHNESS_COLUMN_TYPES,
    SOURCE_FRESHNESS_COLUMNS,
    SOURCE_FRESHNESS_TABLE_NAME,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.sql_values.main.render_state_literal import render_state_sql_literal


def render_insert_source_freshness_records_sql(
    *,
    database: str | None,
    schema: str,
    records: tuple[SourceFreshnessRecord, ...],
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Render DML that appends source freshness records."""

    table_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=SOURCE_FRESHNESS_TABLE_NAME,
    )
    if table_name is None:
        raise AdapterUserError(message="source freshness table requires a target schema")
    values_sql: str = ", ".join(_record_values_sql(record) for record in records)
    return (
        f"INSERT INTO {table_name} ("
        f"{COLUMN_SOURCE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_STRATEGY}, "
        f"{COLUMN_VALUE_KIND}, "
        f"{COLUMN_DATA_VERSION}, "
        f"{COLUMN_DATA_VERSION_HASH}, "
        f"{COLUMN_OBSERVED_AT}"
        f") VALUES {values_sql}"
    )


def _record_values_sql(record: SourceFreshnessRecord) -> str:
    values: tuple[object | None, ...] = (
        record.source_name,
        record.target_database,
        record.target_schema,
        record.target_name,
        record.run_id,
        record.strategy,
        record.value_kind,
        record.data_version,
        record.data_version_hash,
        record.observed_at,
    )
    return (
        "("
        + ", ".join(
            render_state_sql_literal(
                value=value, declared_type=SOURCE_FRESHNESS_COLUMN_TYPES[column]
            )
            for column, value in zip(SOURCE_FRESHNESS_COLUMNS, values, strict=True)
        )
        + ")"
    )
