"""Stable constants for append-only model migration state."""

from __future__ import annotations

from sqlbuild.sql_values.types import StateSqlValueType

MIGRATION_TABLE_NAME: str = "_sqlbuild_migrations"
MIGRATION_WRITE_ATTEMPTS: int = 3
MIGRATION_WRITE_RETRY_BASE_SECONDS: float = 0.05

MIGRATION_COLUMNS: tuple[str, ...] = (
    "event_id",
    "target_name",
    "origin_model",
    "origin_database",
    "origin_schema",
    "origin_name",
    "destination_model",
    "destination_database",
    "destination_schema",
    "destination_name",
    "origin_version_hash",
    "discovery",
    "decision",
    "run_id",
    "created_at",
)

MIGRATION_COLUMN_TYPES: dict[str, StateSqlValueType] = {
    **{column: StateSqlValueType.STRING for column in MIGRATION_COLUMNS},
    "created_at": StateSqlValueType.TEXT_TIMESTAMP,
}
