"""SQL generation helpers for fingerprint storage."""

from __future__ import annotations

import base64
from collections.abc import Callable

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.compiler.fingerprints.constants import (
    COLUMN_AST_HASH,
    COLUMN_MODEL_NAME,
    COLUMN_QUERY_HASH,
    COLUMN_QUERY_SQL,
    COLUMN_RUN_ID,
    COLUMN_SCHEMA_FINGERPRINT,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_NAME,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TIMESTAMP,
    FINGERPRINT_TABLE_NAME,
)


def build_qualified_table_name(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build the fully qualified fingerprint table name for a target schema."""

    qualified_name: str | None = render_qualified_name(
        database=database,
        schema=schema,
        name=FINGERPRINT_TABLE_NAME,
    )
    if qualified_name is None:
        raise ValueError("fingerprint table requires a target schema")
    return qualified_name


def build_create_table_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement for the fingerprint table."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    string_type: str = render_framework_type(FrameworkType.STRING)
    timestamp_type: str = render_framework_type(FrameworkType.TIMESTAMP)
    return (
        f"CREATE TABLE IF NOT EXISTS {qualified_name} ("
        f"{COLUMN_MODEL_NAME} {string_type} NOT NULL, "
        f"{COLUMN_TARGET_DATABASE} {string_type}, "
        f"{COLUMN_TARGET_SCHEMA} {string_type}, "
        f"{COLUMN_TARGET_NAME} {string_type}, "
        f"{COLUMN_RUN_ID} {string_type} NOT NULL, "
        f"{COLUMN_QUERY_HASH} {string_type} NOT NULL, "
        f"{COLUMN_AST_HASH} {string_type}, "
        f"{COLUMN_SCHEMA_FINGERPRINT} {string_type} NOT NULL, "
        f"{COLUMN_QUERY_SQL} {string_type} NOT NULL, "
        f"{COLUMN_TIMESTAMP} {timestamp_type} NOT NULL"
        f")"
    )


def build_read_all_sql(
    *, database: str | None, schema: str, render_qualified_name: Callable[..., str | None]
) -> str:
    """Build a SELECT statement to read all fingerprint rows for a schema."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    return (
        f"SELECT "
        f"{COLUMN_MODEL_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_QUERY_HASH}, "
        f"{COLUMN_AST_HASH}, "
        f"{COLUMN_SCHEMA_FINGERPRINT}, "
        f"{COLUMN_QUERY_SQL}, "
        f"{COLUMN_TIMESTAMP} "
        f"FROM {qualified_name}"
    )


def build_insert_sql(
    *,
    database: str | None,
    schema: str,
    model_name: str,
    target_database: str | None,
    target_schema: str | None,
    target_name: str | None,
    run_id: str,
    query_hash: str,
    ast_hash: str | None,
    schema_fingerprint: str,
    query_sql: str,
    ts: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build a complete INSERT statement for appending one fingerprint row."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    encoded_query_sql: str = _encode_query_sql_storage(query_sql).replace("'", "''")
    ast_hash_literal: str = f"'{ast_hash}'" if ast_hash is not None else "NULL"
    target_database_literal: str = _optional_string_literal(target_database)
    target_schema_literal: str = _optional_string_literal(target_schema)
    target_name_literal: str = _optional_string_literal(target_name)
    return (
        f"INSERT INTO {qualified_name} ("
        f"{COLUMN_MODEL_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_QUERY_HASH}, "
        f"{COLUMN_AST_HASH}, "
        f"{COLUMN_SCHEMA_FINGERPRINT}, "
        f"{COLUMN_QUERY_SQL}, "
        f"{COLUMN_TIMESTAMP}"
        f") VALUES ("
        f"'{model_name}', "
        f"{target_database_literal}, "
        f"{target_schema_literal}, "
        f"{target_name_literal}, "
        f"'{run_id}', "
        f"'{query_hash}', "
        f"{ast_hash_literal}, "
        f"'{schema_fingerprint}', "
        f"'{encoded_query_sql}', "
        f"'{ts}'"
        f")"
    )


def build_add_target_columns_sql(
    *,
    database: str | None,
    schema: str,
    render_qualified_name: Callable[..., str | None],
    render_framework_type: Callable[[FrameworkType], str],
) -> tuple[str, ...]:
    """Build best-effort schema migration statements for existing fingerprint tables."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    string_type: str = render_framework_type(FrameworkType.STRING)
    return (
        f"ALTER TABLE {qualified_name} ADD COLUMN {COLUMN_TARGET_DATABASE} {string_type}",
        f"ALTER TABLE {qualified_name} ADD COLUMN {COLUMN_TARGET_SCHEMA} {string_type}",
        f"ALTER TABLE {qualified_name} ADD COLUMN {COLUMN_TARGET_NAME} {string_type}",
    )


def _optional_string_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"


def _encode_query_sql_storage(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")
