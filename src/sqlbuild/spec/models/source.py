"""Structured raw source metadata models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceColumnEntry:
    """One source column entry from sources/*.yml."""

    name: str
    type: str | None = None


@dataclass(frozen=True)
class SourceEntry:
    """One source declaration from sources/*.yml."""

    name: str
    database: str | None = None
    schema: str | None = None
    table: str | None = None
    type_enforcement: bool | None = None
    columns: tuple[SourceColumnEntry, ...] = field(default_factory=tuple)
