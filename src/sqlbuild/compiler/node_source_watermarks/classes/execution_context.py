"""Mutable node source watermark execution context."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkPayload,
    NodeSourceWatermarkRecord,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessIdentity, SourceFreshnessRecord


class NodeSourceWatermarkExecutionContext:
    """In-memory source watermark state for one execution."""

    def __init__(
        self,
        *,
        direct_source_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord],
        direct_source_identities_by_node: dict[
            NodeSourceWatermarkIdentity,
            tuple[SourceFreshnessIdentity, ...],
        ],
        source_identities_by_node: dict[
            NodeSourceWatermarkIdentity,
            tuple[SourceFreshnessIdentity, ...],
        ],
        upstream_node_identities_by_node: dict[
            NodeSourceWatermarkIdentity,
            tuple[NodeSourceWatermarkIdentity, ...],
        ],
        payloads_by_node: dict[NodeSourceWatermarkIdentity, NodeSourceWatermarkPayload]
        | None = None,
        buffered_records: list[NodeSourceWatermarkRecord] | None = None,
    ) -> None:
        self.direct_source_records = direct_source_records
        self.direct_source_identities_by_node = direct_source_identities_by_node
        self.source_identities_by_node = source_identities_by_node
        self.upstream_node_identities_by_node = upstream_node_identities_by_node
        self.payloads_by_node = payloads_by_node or {}
        self.buffered_records = buffered_records or []

    def record_success(
        self,
        *,
        node_identity: NodeSourceWatermarkIdentity,
        payload: NodeSourceWatermarkPayload,
        record: NodeSourceWatermarkRecord,
    ) -> None:
        """Store a computed node payload and buffer its persisted record."""

        self.payloads_by_node[node_identity] = payload
        self.buffered_records.append(record)
