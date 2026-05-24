"""Typed models for ingestr integration loaders."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class IngestrSourceConfig:
    """Configuration for one source loaded by the ingestr integration loader."""

    source_uri: str
    source_table: str
    strategy: str | None = None
    incremental_key: str | None = None
    primary_key: tuple[str, ...] = field(default_factory=tuple)
    columns: str | None = None
    extra_args: tuple[str, ...] = field(default_factory=tuple)
