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

COLUMN_MIGRATION_TABLE_NAME: str = "_sqlbuild_column_migrations"

COLUMN_MIGRATION_COLUMNS: tuple[str, ...] = (
    "event_id",
    "target_name",
    "model_name",
    "relation_database",
    "relation_schema",
    "relation_name",
    "origin_column",
    "destination_column",
    "discovery",
    "decision",
    "run_id",
    "created_at",
)

COLUMN_MIGRATION_COLUMN_TYPES: dict[str, StateSqlValueType] = {
    **{column: StateSqlValueType.STRING for column in COLUMN_MIGRATION_COLUMNS},
    "created_at": StateSqlValueType.TEXT_TIMESTAMP,
}

OLD_NAME_VIEW_TABLE_NAME: str = "_sqlbuild_old_name_views"
OLD_NAME_VIEW_CONFIG_KEY: str = "old_name_view"

OLD_NAME_VIEW_COLUMNS: tuple[str, ...] = (
    "event_id",
    "target_name",
    "event_type",
    "migration_event_id",
    "destination_model",
    "old_database",
    "old_schema",
    "old_name",
    "new_database",
    "new_schema",
    "new_name",
    "view_retention",
    "archive_name",
    "column_aliases",
    "grants_copied",
    "view_sql",
    "expires_at",
    "drop_reason",
    "run_id",
    "created_at",
)

OLD_NAME_VIEW_COLUMN_TYPES: dict[str, StateSqlValueType] = {
    **{column: StateSqlValueType.STRING for column in OLD_NAME_VIEW_COLUMNS},
    "expires_at": StateSqlValueType.TEXT_TIMESTAMP,
    "created_at": StateSqlValueType.TEXT_TIMESTAMP,
}
