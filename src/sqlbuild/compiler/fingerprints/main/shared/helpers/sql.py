"""SQL generation helpers for fingerprint storage."""

from __future__ import annotations

from sqlbuild.compiler.fingerprints.constants import (
    COLUMN_AST_HASH,
    COLUMN_MODEL_NAME,
    COLUMN_QUERY_HASH,
    COLUMN_QUERY_SQL,
    COLUMN_RUN_ID,
    COLUMN_SCHEMA_FINGERPRINT,
    COLUMN_TIMESTAMP,
    FINGERPRINT_TABLE_NAME,
)


def build_qualified_table_name(*, database: str | None, schema: str) -> str:
    """Build the fully qualified fingerprint table name for a target schema."""

    if database is not None:
        return f"{database}.{schema}.{FINGERPRINT_TABLE_NAME}"
    return f"{schema}.{FINGERPRINT_TABLE_NAME}"


def build_create_table_sql(*, database: str | None, schema: str) -> str:
    """Build a CREATE TABLE IF NOT EXISTS statement for the fingerprint table."""

    qualified_name: str = build_qualified_table_name(database=database, schema=schema)
    return (
        f"CREATE TABLE IF NOT EXISTS {qualified_name} ("
        f"{COLUMN_MODEL_NAME} VARCHAR NOT NULL, "
        f"{COLUMN_RUN_ID} VARCHAR NOT NULL, "
        f"{COLUMN_QUERY_HASH} VARCHAR NOT NULL, "
        f"{COLUMN_AST_HASH} VARCHAR, "
        f"{COLUMN_SCHEMA_FINGERPRINT} VARCHAR NOT NULL, "
        f"{COLUMN_QUERY_SQL} VARCHAR NOT NULL, "
        f"{COLUMN_TIMESTAMP} TIMESTAMP NOT NULL"
        f")"
    )


def build_read_all_sql(*, database: str | None, schema: str) -> str:
    """Build a SELECT statement to read all fingerprint rows for a schema."""

    qualified_name: str = build_qualified_table_name(database=database, schema=schema)
    return (
        f"SELECT "
        f"{COLUMN_MODEL_NAME}, "
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
    run_id: str,
    query_hash: str,
    ast_hash: str | None,
    schema_fingerprint: str,
    query_sql: str,
    ts: str,
) -> str:
    """Build a complete INSERT statement for appending one fingerprint row."""

    qualified_name: str = build_qualified_table_name(database=database, schema=schema)
    escaped_query_sql: str = query_sql.replace("'", "''")
    ast_hash_literal: str = f"'{ast_hash}'" if ast_hash is not None else "NULL"
    return (
        f"INSERT INTO {qualified_name} ("
        f"{COLUMN_MODEL_NAME}, "
        f"{COLUMN_RUN_ID}, "
        f"{COLUMN_QUERY_HASH}, "
        f"{COLUMN_AST_HASH}, "
        f"{COLUMN_SCHEMA_FINGERPRINT}, "
        f"{COLUMN_QUERY_SQL}, "
        f"{COLUMN_TIMESTAMP}"
        f") VALUES ("
        f"'{model_name}', "
        f"'{run_id}', "
        f"'{query_hash}', "
        f"{ast_hash_literal}, "
        f"'{schema_fingerprint}', "
        f"'{escaped_query_sql}', "
        f"'{ts}'"
        f")"
    )
