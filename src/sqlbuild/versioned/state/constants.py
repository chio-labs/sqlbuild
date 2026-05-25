"""Versioned state store constants."""

from __future__ import annotations

from sqlbuild.versioned.state.types import StateColumnType

CURRENT_STATE_SCHEMA_VERSION: int = 1

STATE_VERSION_TABLE: str = "state_versions"
STATE_MIGRATION_EVENTS_TABLE: str = "state_migration_events"

STATE_TABLES: tuple[str, ...] = (
    STATE_VERSION_TABLE,
    STATE_MIGRATION_EVENTS_TABLE,
)

STATE_VERSION_COLUMNS: dict[str, StateColumnType] = {
    "schema_version": StateColumnType.INTEGER,
    "sqlbuild_version": StateColumnType.TEXT,
    "updated_at": StateColumnType.TIMESTAMP,
}

STATE_MIGRATION_EVENT_COLUMNS: dict[str, StateColumnType] = {
    "event_id": StateColumnType.TEXT,
    "action": StateColumnType.TEXT,
    "backup_id": StateColumnType.TEXT,
    "status": StateColumnType.TEXT,
    "message": StateColumnType.TEXT,
    "created_at": StateColumnType.TIMESTAMP,
}

STATE_TABLE_COLUMNS: dict[str, dict[str, StateColumnType]] = {
    STATE_VERSION_TABLE: STATE_VERSION_COLUMNS,
    STATE_MIGRATION_EVENTS_TABLE: STATE_MIGRATION_EVENT_COLUMNS,
}
