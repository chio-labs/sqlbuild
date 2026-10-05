from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompactJobSnapshotCase:
    description: str
    query_sql: str
    prepared_types: dict[str, str]
    updated_types: dict[str, str]
    expected_changed_by_update: bool


@dataclass(frozen=True)
class CompactJobRerunCase:
    description: str
    query_sql: str
    expected_error: str


@dataclass(frozen=True)
class ConcurrentCompactJobCase:
    description: str
    job_count: int
    prepared_types: dict[str, str]
    expected_matches_serial: bool
