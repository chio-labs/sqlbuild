"""SQL generation helpers for standard source freshness storage."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.adapter.shared.types import FrameworkType
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
from sqlbuild.compiler.source_freshness.exceptions import SourceFreshnessInputError


def build_qualified_table_name(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build the fully qualified source freshness table name for a target schema."""

    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=SOURCE_FRESHNESS_TABLE_NAME,
    )
    if qualified_name is None:
        raise SourceFreshnessInputError("source freshness table requires a target schema")
    return qualified_name


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement for source freshness state."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    string_type: str = render_framework_type(FrameworkType.STRING)
    timestamp_type: str = render_framework_type(FrameworkType.TIMESTAMP)
    return (
        f"CREATE TABLE IF NOT EXISTS {qualified_name} ("
        f"{COLUMN_SOURCE_NAME} {string_type} NOT NULL, "
        f"{COLUMN_TARGET_DATABASE} {string_type}, "
        f"{COLUMN_TARGET_SCHEMA} {string_type}, "
        f"{COLUMN_TARGET_NAME} {string_type}, "
        f"{COLUMN_RUN_ID} {string_type} NOT NULL, "
        f"{COLUMN_STRATEGY} {string_type} NOT NULL, "
        f"{COLUMN_VALUE_KIND} {string_type} NOT NULL, "
        f"{COLUMN_DATA_VERSION} {string_type}, "
        f"{COLUMN_DATA_VERSION_HASH} {string_type} NOT NULL, "
        f"{COLUMN_OBSERVED_AT} {timestamp_type} NOT NULL"
        f")"
    )


def build_read_all_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    """Build a SELECT statement to read all source freshness rows for a schema."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    return (
        f"SELECT "
        f"{COLUMN_SOURCE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_STRATEGY}, "
        f"{COLUMN_VALUE_KIND}, "
        f"{COLUMN_DATA_VERSION}, "
        f"{COLUMN_DATA_VERSION_HASH}, "
        f"{COLUMN_OBSERVED_AT} "
        f"FROM {qualified_name}"
    )


def build_insert_sql(
    *,
    database: str | None,
    schema: str,
    source_name: str,
    target_database: str | None,
    target_schema: str | None,
    target_name: str | None,
    run_id: str,
    strategy: str,
    value_kind: str,
    data_version: str | None,
    data_version_hash: str,
    observed_at: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build a complete INSERT statement for appending one source freshness row."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    return (
        f"INSERT INTO {qualified_name} ("
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
        f") VALUES ("
        f"{_required_string_literal(source_name)}, "
        f"{_optional_string_literal(target_database)}, "
        f"{_optional_string_literal(target_schema)}, "
        f"{_optional_string_literal(target_name)}, "
        f"{_required_string_literal(run_id)}, "
        f"{_required_string_literal(strategy)}, "
        f"{_required_string_literal(value_kind)}, "
        f"{_optional_string_literal(data_version)}, "
        f"{_required_string_literal(data_version_hash)}, "
        f"{_required_string_literal(observed_at)}"
        f")"
    )


def _optional_string_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return _required_string_literal(value)


def _required_string_literal(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"
