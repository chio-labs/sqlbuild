"""Stable constants for fingerprint storage."""

from __future__ import annotations

FINGERPRINT_TABLE_NAME: str = "_sqlbuild_fingerprints"

COLUMN_MODEL_NAME: str = "model_name"
COLUMN_TARGET_DATABASE: str = "target_database"
COLUMN_TARGET_SCHEMA: str = "target_schema"
COLUMN_TARGET_NAME: str = "target_name"
COLUMN_RUN_ID: str = "run_id"
COLUMN_QUERY_HASH: str = "query_hash"
COLUMN_AST_HASH: str = "ast_hash"
COLUMN_SCHEMA_FINGERPRINT: str = "schema_fingerprint"
COLUMN_QUERY_SQL_B64: str = "query_sql_b64"
COLUMN_METADATA_JSON_B64: str = "metadata_json_b64"
COLUMN_TIMESTAMP: str = "ts"

FINGERPRINT_COLUMNS: tuple[str, ...] = (
    COLUMN_MODEL_NAME,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TARGET_NAME,
    COLUMN_RUN_ID,
    COLUMN_QUERY_HASH,
    COLUMN_AST_HASH,
    COLUMN_SCHEMA_FINGERPRINT,
    COLUMN_QUERY_SQL_B64,
    COLUMN_METADATA_JSON_B64,
    COLUMN_TIMESTAMP,
)
