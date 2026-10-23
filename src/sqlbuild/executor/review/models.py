"""Review schema domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReviewSchemaMarker:
    """Where one review schema lives and where its ownership marker is written."""

    database: str | None
    schema: str
    marker_database: str | None
    marker_schema: str
    run_id: str


@dataclass(frozen=True)
class LeftoverReviewSchema:
    """A review schema an earlier run created and did not drop."""

    database: str | None
    schema: str
    created_at: datetime

    def display_name(self) -> str:
        """Render a qualified schema display name."""

        return self.schema if self.database is None else f"{self.database}.{self.schema}"
