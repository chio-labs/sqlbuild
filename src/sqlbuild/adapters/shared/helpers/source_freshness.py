"""Shared adapter renderers for source freshness state."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.shared.exceptions import AdapterUserError
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
    SOURCE_FRESHNESS_TABLE_NAME,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord


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
        raise AdapterUserError("source freshness table requires a target schema")
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
    return (
        "("
        f"{_quote_sql_string(record.source_name)}, "
        f"{_optional_string(record.target_database)}, "
        f"{_optional_string(record.target_schema)}, "
        f"{_optional_string(record.target_name)}, "
        f"{_quote_sql_string(record.run_id)}, "
        f"{_quote_sql_string(record.strategy)}, "
        f"{_quote_sql_string(record.value_kind)}, "
        f"{_optional_string(record.data_version)}, "
        f"{_quote_sql_string(record.data_version_hash)}, "
        f"{_quote_sql_string(record.observed_at.isoformat())}"
        ")"
    )


def _optional_string(value: str | None) -> str:
    if value is None:
        return "NULL"
    return _quote_sql_string(value)


def _quote_sql_string(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
