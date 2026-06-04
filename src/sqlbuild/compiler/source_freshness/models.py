"""Direct source freshness state models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind


@dataclass(frozen=True)
class SourceFreshnessObservation:
    """One comparable source data-version observation."""

    source_name: str
    strategy: SourceFreshnessStrategy
    data_version: object
    value_kind: SourceFreshnessValueKind
    observed_at: datetime


@dataclass(frozen=True)
class SourceFreshnessIdentity:
    """Stable identity for one source freshness stream in direct state."""

    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None


@dataclass(frozen=True)
class SourceFreshnessRecord:
    """One append-only direct source freshness observation."""

    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    strategy: str
    value_kind: str
    data_version: str | None
    data_version_hash: str
    observed_at: datetime

    @property
    def identity(self) -> SourceFreshnessIdentity:
        return SourceFreshnessIdentity(
            source_name=self.source_name,
            target_database=self.target_database,
            target_schema=self.target_schema,
            target_name=self.target_name,
        )


@dataclass(frozen=True)
class SourceFreshnessSet:
    """Latest direct source freshness records for one target schema."""

    schema: str
    records: dict[SourceFreshnessIdentity, SourceFreshnessRecord]
