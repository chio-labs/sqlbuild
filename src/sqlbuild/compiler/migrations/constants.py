"""Stable constants for append-only model migration state."""

from __future__ import annotations

MIGRATION_TABLE_NAME: str = "_sqlbuild_migrations"
MIGRATION_WRITE_ATTEMPTS: int = 3
MIGRATION_WRITE_RETRY_BASE_SECONDS: float = 0.05

COLUMN_MIGRATION_TABLE_NAME: str = "_sqlbuild_column_migrations"

OLD_NAME_VIEW_TABLE_NAME: str = "_sqlbuild_old_name_views"
