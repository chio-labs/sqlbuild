"""Stable constants for fingerprint storage."""

from __future__ import annotations

FINGERPRINT_TABLE_NAME: str = "_sqlbuild_fingerprints"

FINGERPRINT_WRITE_ATTEMPTS: int = 5
FINGERPRINT_WRITE_RETRY_BASE_SECONDS: float = 0.05

COLUMN_NODE_TYPE: str = "node_type"
COLUMN_NODE_NAME: str = "node_name"
COLUMN_TARGET_DATABASE: str = "target_database"
COLUMN_TARGET_SCHEMA: str = "target_schema"
COLUMN_TARGET_NAME: str = "target_name"
COLUMN_RUN_ID: str = "run_id"
COLUMN_DEFINITION_HASH: str = "definition_hash"
COLUMN_VERSION_HASH: str = "version_hash"
COLUMN_SCHEMA_FINGERPRINT: str = "schema_fingerprint"
COLUMN_DEFINITION_B64: str = "definition_b64"
COLUMN_METADATA_JSON_B64: str = "metadata_json_b64"
COLUMN_TIMESTAMP: str = "ts"

NODE_TYPE_MODEL: str = "model"
NODE_TYPE_UDF: str = "udf"
NODE_TYPE_TABLE_FN: str = "table_fn"
FUNCTION_NODE_TYPES: tuple[str, str] = (NODE_TYPE_UDF, NODE_TYPE_TABLE_FN)
NODE_TYPE_SEED: str = "seed"
NODE_TYPE_LOADER: str = "loader"
NODE_TYPE_TASK: str = "task"
NODE_TYPE_ASSET: str = "asset"
NODE_TYPE_CHECK: str = "check"
NODE_TYPE_HOOK: str = "hook"

FINGERPRINT_COLUMNS: tuple[str, ...] = (
    COLUMN_NODE_TYPE,
    COLUMN_NODE_NAME,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TARGET_NAME,
    COLUMN_RUN_ID,
    COLUMN_DEFINITION_HASH,
    COLUMN_VERSION_HASH,
    COLUMN_SCHEMA_FINGERPRINT,
    COLUMN_DEFINITION_B64,
    COLUMN_METADATA_JSON_B64,
    COLUMN_TIMESTAMP,
)
