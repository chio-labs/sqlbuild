"""Standard node source watermark state models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlbuild.compiler.node_source_watermarks.types import (
    WatermarkGraphResourceKind,
    WatermarkStalenessStatus,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)


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


@dataclass(frozen=True)
class NodeSourceWatermarkTarget:
    """Physical target relation for a materialized node watermark row."""

    database: str | None
    schema: str | None
    name: str | None


@dataclass(frozen=True)
class NativeNodeSourceWatermarkInputs:
    """Native plan-derived source watermark execution inputs."""

    frontier_members: tuple[WatermarkFrontierMember, ...] = ()
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode] = field(default_factory=dict)
    source_identities_by_key: dict[WatermarkGraphKey, SourceFreshnessIdentity] = field(
        default_factory=dict
    )
    source_identities_by_node: dict[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ] = field(default_factory=dict)
    direct_source_identities_by_node: dict[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ] = field(default_factory=dict)
    upstream_node_identities_by_node: dict[
        NodeSourceWatermarkIdentity,
        tuple[NodeSourceWatermarkIdentity, ...],
    ] = field(default_factory=dict)


@dataclass(frozen=True)
class WatermarkGraphKey:
    """Framework-neutral graph key for watermark frontier analysis."""

    node_type: str
    node_name: str


@dataclass(frozen=True)
class WatermarkGraphNode:
    """Framework-neutral graph node metadata for watermark frontier analysis."""

    key: WatermarkGraphKey
    resource_kind: WatermarkGraphResourceKind | str
    materialized: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_kind",
            WatermarkGraphResourceKind(self.resource_kind),
        )


@dataclass(frozen=True)
class WatermarkFrontierMember:
    """One materialized/source frontier node reached from a selected root."""

    root_key: WatermarkGraphKey
    frontier_key: WatermarkGraphKey


@dataclass(frozen=True)
class WatermarkSourceAncestryMember:
    """One raw source ancestor reached from a graph node."""

    node_key: WatermarkGraphKey
    source_key: WatermarkGraphKey


@dataclass(frozen=True)
class NodeSourceWatermarkStaleness:
    """Freshness classification for one frontier source proof."""

    root_key: WatermarkGraphKey
    frontier_key: WatermarkGraphKey
    source_identity: SourceFreshnessIdentity
    status: WatermarkStalenessStatus
    reason: str | None = None
    watermark_entry: SourceWatermarkEntry | None = None
    current_record: SourceFreshnessRecord | None = None


@dataclass(frozen=True)
class NodeSourceWatermarkStalenessReport:
    """Grouped stale-input report derived from source watermark classifications."""

    affected_root_names: tuple[str, ...] = ()
    stale_frontier_names: tuple[str, ...] = ()
    changed_source_names: tuple[str, ...] = ()
    unknown_frontier_names: tuple[str, ...] = ()

    @property
    def has_entries(self) -> bool:
        return bool(
            self.affected_root_names
            or self.stale_frontier_names
            or self.changed_source_names
            or self.unknown_frontier_names
        )


from sqlbuild.compiler.node_source_watermarks.classes.execution_context import (  # noqa: E402,F401
    NodeSourceWatermarkExecutionContext,
)
