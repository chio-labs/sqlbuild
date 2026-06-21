"""Typed models for dlt integration loaders."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DltResourceConfig:
    """One SQLBuild-managed dlt resource inside a declarative source group."""

    name: str
    dlt_name: str
    raw_config: dict[str, object]
    write_disposition: object | None = None
    primary_key: object | None = None
    merge_key: object | None = None
    incremental: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class DltSourceConfig:
    """Configuration for one dlt resource loaded by a synthetic loader."""

    source_type: str
    config: dict[str, object]
    resource: DltResourceConfig
    group_index: int


@dataclass(frozen=True)
class DltDestinationConfig:
    """Resolved dlt destination and dataset for a SQLBuild target."""

    destination: Any
    dataset_name: str | None
