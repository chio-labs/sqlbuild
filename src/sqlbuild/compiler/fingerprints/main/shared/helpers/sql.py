"""SQL generation helpers for fingerprint storage."""

from __future__ import annotations

import base64
from collections.abc import Callable

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.compiler.fingerprints.constants import (
    COLUMN_DEFINITION_B64,
    COLUMN_DEFINITION_HASH,
    COLUMN_METADATA_JSON_B64,
    COLUMN_NODE_NAME,
    COLUMN_NODE_TYPE,
    COLUMN_RUN_ID,
    COLUMN_SCHEMA_FINGERPRINT,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_NAME,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TIMESTAMP,
    COLUMN_VERSION_HASH,
    FINGERPRINT_TABLE_NAME,
)
from sqlbuild.compiler.fingerprints.exceptions import FingerprintInputError


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
        raise FingerprintInputError("fingerprint table requires a target schema")
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
        f"{COLUMN_NODE_TYPE} {string_type} NOT NULL, "
        f"{COLUMN_NODE_NAME} {string_type} NOT NULL, "
        f"{COLUMN_TARGET_DATABASE} {string_type}, "
        f"{COLUMN_TARGET_SCHEMA} {string_type}, "
        f"{COLUMN_TARGET_NAME} {string_type}, "
        f"{COLUMN_RUN_ID} {string_type} NOT NULL, "
        f"{COLUMN_DEFINITION_HASH} {string_type} NOT NULL, "
        f"{COLUMN_VERSION_HASH} {string_type} NOT NULL, "
        f"{COLUMN_SCHEMA_FINGERPRINT} {string_type} NOT NULL, "
        f"{COLUMN_DEFINITION_B64} {string_type} NOT NULL, "
        f"{COLUMN_METADATA_JSON_B64} {string_type} NOT NULL, "
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
        f"{COLUMN_NODE_TYPE}, "
        f"{COLUMN_NODE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_DEFINITION_HASH}, "
        f"{COLUMN_VERSION_HASH}, "
        f"{COLUMN_SCHEMA_FINGERPRINT}, "
        f"{COLUMN_DEFINITION_B64}, "
        f"{COLUMN_METADATA_JSON_B64}, "
        f"{COLUMN_TIMESTAMP} "
        f"FROM {qualified_name}"
    )


def build_insert_sql(
    *,
    database: str | None,
    schema: str,
    node_type: str,
    node_name: str,
    target_database: str | None,
    target_schema: str | None,
    target_name: str | None,
    run_id: str,
    definition_hash: str,
    version_hash: str,
    schema_fingerprint: str,
    definition: str,
    metadata_json: str,
    ts: str,
    render_qualified_name: Callable[..., str | None],
) -> str:
    """Build a complete INSERT statement for appending one fingerprint row."""

    qualified_name: str = build_qualified_table_name(
        database=database,
        schema=schema,
        render_qualified_name=render_qualified_name,
    )
    encoded_definition: str = _encode_definition_storage(definition).replace("'", "''")
    encoded_metadata_json: str = _encode_definition_storage(metadata_json).replace("'", "''")
    node_type_literal: str = _required_string_literal(node_type)
    node_name_literal: str = _required_string_literal(node_name)
    target_database_literal: str = _optional_string_literal(target_database)
    target_schema_literal: str = _optional_string_literal(target_schema)
    target_name_literal: str = _optional_string_literal(target_name)
    return (
        f"INSERT INTO {qualified_name} ("
        f"{COLUMN_NODE_TYPE}, "
        f"{COLUMN_NODE_NAME}, "
        f"{COLUMN_TARGET_DATABASE}, "
        f"{COLUMN_TARGET_SCHEMA}, "
        f"{COLUMN_TARGET_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_DEFINITION_HASH}, "
        f"{COLUMN_VERSION_HASH}, "
        f"{COLUMN_SCHEMA_FINGERPRINT}, "
        f"{COLUMN_DEFINITION_B64}, "
        f"{COLUMN_METADATA_JSON_B64}, "
        f"{COLUMN_TIMESTAMP}"
        f") VALUES ("
        f"{node_type_literal}, "
        f"{node_name_literal}, "
        f"{target_database_literal}, "
        f"{target_schema_literal}, "
        f"{target_name_literal}, "
        f"'{run_id}', "
        f"'{definition_hash}', "
        f"'{version_hash}', "
        f"'{schema_fingerprint}', "
        f"'{encoded_definition}', "
        f"'{encoded_metadata_json}', "
        f"'{ts}'"
        f")"
    )


def _optional_string_literal(value: str | None) -> str:
    if value is None:
        return "NULL"
    return _required_string_literal(value)


def _required_string_literal(value: str) -> str:
    escaped_value: str = value.replace("'", "''")
    return f"'{escaped_value}'"


def _encode_definition_storage(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")
