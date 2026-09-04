from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlbuild.cli.commands.models import FreshnessCommandResult
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord


@dataclass(frozen=True)
class FreshnessOutputTestCase:
    description: str
    result: FreshnessCommandResult
    expected_text_fragments: tuple[str, ...]
    expected_color_fragments: tuple[str, ...]
    expected_summary: dict[str, int]
    expected_json_age_statuses: dict[str, str | None]


@dataclass(frozen=True)
class FreshnessObservationTestCase:
    description: str
    select: tuple[str, ...]
    exclude: tuple[str, ...]
    expected_statuses: dict[str, str]
    expected_versions: dict[str, str]
    previous_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] | None = None
    expected_age_statuses: dict[str, str] | None = None
    observed_at: datetime = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
