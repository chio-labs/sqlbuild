"""Planner domain models."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlbuild.adapter.shared.models import ColumnInfo, RelationInfo
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.types import SelectorKind


@dataclass(frozen=True)
class ParsedSelector:
    """One parsed selector token before graph resolution."""

    kind: SelectorKind
    value: str
    upstream: bool = False
    downstream: bool = False


@dataclass(frozen=True)
class WarehouseSnapshot:
    """Frozen point-in-time picture of warehouse state for planning."""

    existing_relations: dict[str, RelationInfo] = field(default_factory=dict)
    existing_columns: dict[str, tuple[ColumnInfo, ...]] = field(default_factory=dict)
    fingerprints: dict[str, Fingerprint] = field(default_factory=dict)
