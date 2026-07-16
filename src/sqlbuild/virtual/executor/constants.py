"""Virtual executor constants."""

from __future__ import annotations

DUCKDB_MEMORY_DATABASE: str = ":memory:"
VIRTUAL_CLONE_HYDRATED_ACTION: str = "hydrated"
VIRTUAL_CLONE_REUSED_ACTION: str = "reused"
VIRTUAL_CLONE_MISSING_ACTION: str = "missing"
VIRTUAL_CLONE_SKIPPED_LOCKED_ACTION: str = "skipped_locked"
VIRTUAL_CLONE_FOUND_ACTIONS: tuple[str, ...] = (
    VIRTUAL_CLONE_HYDRATED_ACTION,
    VIRTUAL_CLONE_REUSED_ACTION,
)
