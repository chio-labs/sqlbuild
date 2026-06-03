"""Source freshness observation models for virtual environments."""

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
