"""Source freshness observation models for virtual environments."""

from __future__ import annotations

from dataclasses import dataclass

from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessObservation as SourceFreshnessObservation,
)
from sqlbuild.virtual.state.models import SourceFreshnessRecord


@dataclass(frozen=True)
class SourceFreshnessRuntimeResult:
    """Result of observing source freshness for one virtual environment."""

    records: tuple[SourceFreshnessRecord, ...]
    unknown_source_names: tuple[str, ...] = ()
    preserved_source_names: tuple[str, ...] = ()
    generated_source_names: tuple[str, ...] = ()
