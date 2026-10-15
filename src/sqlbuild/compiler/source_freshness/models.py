"""Direct source freshness state models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild._native import (
    SourceFreshnessIdentity,
    require_aware_utc_datetime,
)


@dataclass(frozen=True)
class SourceFreshnessRecord:
    """One append-only direct observation whose observed time is always aware UTC."""

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

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_at",
            require_aware_utc_datetime(value=self.observed_at, field_name="observed_at"),
        )

    @property
    def identity(self) -> SourceFreshnessIdentity:
        return SourceFreshnessIdentity(
            source_name=self.source_name,
            target_database=self.target_database,
            target_schema=self.target_schema,
            target_name=self.target_name,
        )
