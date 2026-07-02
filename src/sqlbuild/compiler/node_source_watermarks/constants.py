"""Stable constants for standard node source watermark storage."""

from __future__ import annotations

NODE_SOURCE_WATERMARK_TABLE_NAME: str = "_sqlbuild_node_source_watermarks"

COLUMN_NODE_TYPE: str = "node_type"
COLUMN_NODE_NAME: str = "node_name"
COLUMN_TARGET_DATABASE: str = "target_database"
COLUMN_TARGET_SCHEMA: str = "target_schema"
COLUMN_TARGET_NAME: str = "target_name"
COLUMN_RUN_ID: str = "run_id"
COLUMN_NODE_VERSION_HASH: str = "node_version_hash"
COLUMN_WATERMARKS_JSON_B64: str = "watermarks_json_b64"
COLUMN_CREATED_AT: str = "created_at"

NODE_SOURCE_WATERMARK_COLUMNS: tuple[str, ...] = (
    COLUMN_NODE_TYPE,
    COLUMN_NODE_NAME,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TARGET_NAME,
    COLUMN_RUN_ID,
    COLUMN_NODE_VERSION_HASH,
    COLUMN_WATERMARKS_JSON_B64,
    COLUMN_CREATED_AT,
)
