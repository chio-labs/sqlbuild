"""BigQuery adapter models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UsageQuery:
    """One INFORMATION_SCHEMA.JOBS read: its SQL, location, window and table names."""

    sql: str
    location: str
    window_seconds: int
    object_names: tuple[str, ...]
