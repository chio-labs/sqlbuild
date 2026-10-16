from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlbuild._native import SourceFreshnessIdentity, SourceFreshnessRecord


@dataclass(frozen=True)
class FreshnessObservationTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_statuses: dict[str, str]
    expected_versions: dict[str, str]
    previous_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] | None = None
    expected_age_statuses: dict[str, str] = field(default_factory=dict)
    observed_at: datetime = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
