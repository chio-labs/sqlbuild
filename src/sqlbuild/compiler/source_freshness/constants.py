"""Stable constants for direct source freshness storage."""

from __future__ import annotations

from sqlbuild.sql_values.types import StateSqlValueType

SOURCE_FRESHNESS_TABLE_NAME: str = "_sqlbuild_source_freshness"
PHYSICAL_TABLE_SOURCE_ERROR_FRAGMENT: str = "requires a physical table source"
INCOMPLETE_CONFIGURATION_ERROR_FRAGMENT: str = "incomplete"

COLUMN_SOURCE_NAME: str = "source_name"
COLUMN_TARGET_DATABASE: str = "target_database"
COLUMN_TARGET_SCHEMA: str = "target_schema"
COLUMN_TARGET_NAME: str = "target_name"
COLUMN_RUN_ID: str = "run_id"
COLUMN_STRATEGY: str = "strategy"
COLUMN_VALUE_KIND: str = "value_kind"
COLUMN_DATA_VERSION: str = "data_version"
COLUMN_DATA_VERSION_HASH: str = "data_version_hash"
COLUMN_OBSERVED_AT: str = "observed_at"

SOURCE_FRESHNESS_COLUMNS: tuple[str, ...] = (
    COLUMN_SOURCE_NAME,
    COLUMN_TARGET_DATABASE,
    COLUMN_TARGET_SCHEMA,
    COLUMN_TARGET_NAME,
    COLUMN_RUN_ID,
    COLUMN_STRATEGY,
    COLUMN_VALUE_KIND,
    COLUMN_DATA_VERSION,
    COLUMN_DATA_VERSION_HASH,
    COLUMN_OBSERVED_AT,
)

SOURCE_FRESHNESS_COLUMN_TYPES: dict[str, StateSqlValueType] = {
    COLUMN_SOURCE_NAME: StateSqlValueType.STRING,
    COLUMN_TARGET_DATABASE: StateSqlValueType.STRING,
    COLUMN_TARGET_SCHEMA: StateSqlValueType.STRING,
    COLUMN_TARGET_NAME: StateSqlValueType.STRING,
    COLUMN_RUN_ID: StateSqlValueType.STRING,
    COLUMN_STRATEGY: StateSqlValueType.STRING,
    COLUMN_VALUE_KIND: StateSqlValueType.STRING,
    COLUMN_DATA_VERSION: StateSqlValueType.STRING,
    COLUMN_DATA_VERSION_HASH: StateSqlValueType.STRING,
    COLUMN_OBSERVED_AT: StateSqlValueType.TEXT_TIMESTAMP,
}
