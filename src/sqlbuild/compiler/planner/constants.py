"""Planner domain constants."""

from __future__ import annotations

MICROBATCH_START_SENTINEL: str = "__SQB_CURSOR_START__"
MICROBATCH_END_SENTINEL: str = "__SQB_CURSOR_END__"
MIGRATION_FINGERPRINT_METADATA_KEY: str = "migration_fingerprint"
SNAPSHOT_DEFAULT_VALID_FROM_COLUMN: str = "valid_from"
SNAPSHOT_DEFAULT_VALID_TO_COLUMN: str = "valid_to"
