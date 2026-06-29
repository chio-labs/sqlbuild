"""Standard node source watermark state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class NodeSourceWatermarkIdentity:
    """Stable identity for one materialized node watermark stream."""

    node_type: str
    node_name: str


@dataclass(frozen=True)
class SourceWatermarkEntry:
    """Effective source watermark that reached a materialized node."""

    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    strategy: str
    value_kind: str
    data_version: str | None
    data_version_hash: str
    observed_at: datetime
    watermark_kind: str


@dataclass(frozen=True)
class UnknownSourceWatermarkEntry:
    """Source ancestry whose effective watermark could not be proven."""

    source_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    reason: str


@dataclass(frozen=True)
class NodeSourceWatermarkPayload:
    """Structured source watermark payload stored as base64 JSON."""

    version: int
    complete: bool
    sources: tuple[SourceWatermarkEntry, ...] = ()
    unknown_sources: tuple[UnknownSourceWatermarkEntry, ...] = ()


@dataclass(frozen=True)
class NodeSourceWatermarkRecord:
    """One append-only materialized node source watermark snapshot."""

    node_type: str
    node_name: str
    target_database: str | None
    target_schema: str | None
    target_name: str | None
    run_id: str
    node_version_hash: str
    payload: NodeSourceWatermarkPayload
    created_at: datetime

    @property
    def identity(self) -> NodeSourceWatermarkIdentity:
        return NodeSourceWatermarkIdentity(
            node_type=self.node_type,
            node_name=self.node_name,
        )


@dataclass(frozen=True)
class NodeSourceWatermarkSet:
    """Latest node source watermark records for one target schema."""

    schema: str
    records: dict[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord] = field(
        default_factory=dict
    )
