"""Source freshness observation models for virtual environments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlbuild.spec.models.types import SourceFreshnessStrategy, SourceFreshnessValueKind
from sqlbuild.virtual.state.models import SourceFreshnessRecord


@dataclass(frozen=True)
class SourceFreshnessObservation:
    """One comparable source data-version observation."""

    source_name: str
    strategy: SourceFreshnessStrategy
    data_version: object
    value_kind: SourceFreshnessValueKind
    observed_at: datetime


@dataclass(frozen=True)
class SourceFreshnessRuntimeResult:
    """Result of observing source freshness for one virtual environment."""

    records: tuple[SourceFreshnessRecord, ...]
    unknown_source_names: tuple[str, ...] = ()
    preserved_source_names: tuple[str, ...] = ()
    generated_source_names: tuple[str, ...] = ()
