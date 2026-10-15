"""Planner domain constants."""

from __future__ import annotations

from sqlbuild._native import cursor_sentinel_to_token as sentinel_to_token
from sqlbuild.cursor_algebra.types import BoundSentinel

SELECTOR_KIND_SEPARATOR: str = ":"
MICROBATCH_START_SENTINEL: str = sentinel_to_token(sentinel=BoundSentinel.START)
MICROBATCH_END_SENTINEL: str = sentinel_to_token(sentinel=BoundSentinel.END)
MIGRATION_FINGERPRINT_METADATA_KEY: str = "migration_fingerprint"
SNAPSHOT_DEFAULT_VALID_FROM_COLUMN: str = "valid_from"
SNAPSHOT_DEFAULT_VALID_TO_COLUMN: str = "valid_to"
