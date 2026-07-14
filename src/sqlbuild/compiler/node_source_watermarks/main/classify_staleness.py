"""Public node source watermark staleness classifier entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.node_source_watermarks._helpers.classifier import (
    classify_node_source_watermark_staleness as _classify_node_source_watermark_staleness,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkStaleness,
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)


def classify_node_source_watermark_staleness(
    *,
    frontier_members: tuple[WatermarkFrontierMember, ...],
    nodes: Mapping[WatermarkGraphKey, WatermarkGraphNode],
    source_identities_by_key: Mapping[WatermarkGraphKey, SourceFreshnessIdentity],
    required_source_identities_by_node: Mapping[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ],
    current_source_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord],
    watermark_records: Mapping[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord],
) -> tuple[NodeSourceWatermarkStaleness, ...]:
    """Classify each selected frontier source as fresh, stale, or unknown."""

    return _classify_node_source_watermark_staleness(
        frontier_members=frontier_members,
        nodes=nodes,
        source_identities_by_key=source_identities_by_key,
        required_source_identities_by_node=required_source_identities_by_node,
        current_source_records=current_source_records,
        watermark_records=watermark_records,
    )
