"""Staleness classification helpers for node source watermarks."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkStaleness,
    SourceWatermarkEntry,
    UnknownSourceWatermarkEntry,
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
)
from sqlbuild.compiler.node_source_watermarks.types import (
    WatermarkGraphResourceKind,
    WatermarkStalenessStatus,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)

_MISSING_CURRENT_SOURCE_FRESHNESS: str = "missing_current_source_freshness"
_MISSING_SOURCE_WATERMARK: str = "missing_source_watermark"
_MISSING_FRONTIER_WATERMARK: str = "missing_frontier_watermark"


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

    classifications: list[NodeSourceWatermarkStaleness] = []
    member: WatermarkFrontierMember
    for member in frontier_members:
        frontier_node: WatermarkGraphNode | None = nodes.get(member.frontier_key)
        if frontier_node is None:
            continue
        if frontier_node.resource_kind == WatermarkGraphResourceKind.SOURCE:
            source_identity: SourceFreshnessIdentity | None = source_identities_by_key.get(
                member.frontier_key
            )
            if source_identity is None:
                continue
            classifications.append(
                _classify_source_against_record(
                    member=member,
                    source_identity=source_identity,
                    record_identity=_identity_from_graph_key(member.root_key),
                    current_source_records=current_source_records,
                    watermark_records=watermark_records,
                )
            )
            continue
        if not frontier_node.materialized:
            continue
        record_identity: NodeSourceWatermarkIdentity = _identity_from_graph_key(member.frontier_key)
        source_identities: tuple[SourceFreshnessIdentity, ...] = (
            required_source_identities_by_node.get(record_identity, ())
        )
        record: NodeSourceWatermarkRecord | None = watermark_records.get(record_identity)
        if record is None:
            missing_source_identity: SourceFreshnessIdentity
            for missing_source_identity in source_identities:
                classifications.append(
                    _unknown_classification(
                        member=member,
                        source_identity=missing_source_identity,
                        reason=_MISSING_FRONTIER_WATERMARK,
                        current_record=current_source_records.get(missing_source_identity),
                    )
                )
            continue
        source_entry: SourceWatermarkEntry
        for source_entry in record.payload.sources:
            classifications.append(
                _classify_entry(
                    member=member,
                    source_identity=_identity_from_entry(source_entry),
                    entry=source_entry,
                    current_source_records=current_source_records,
                )
            )
        unknown_entry: UnknownSourceWatermarkEntry
        for unknown_entry in record.payload.unknown_sources:
            unknown_identity: SourceFreshnessIdentity = _identity_from_unknown_entry(unknown_entry)
            classifications.append(
                _unknown_classification(
                    member=member,
                    source_identity=unknown_identity,
                    reason=unknown_entry.reason,
                    current_record=current_source_records.get(unknown_identity),
                )
            )
    return tuple(sorted(classifications, key=_classification_sort_key))


def _classify_source_against_record(
    *,
    member: WatermarkFrontierMember,
    source_identity: SourceFreshnessIdentity,
    record_identity: NodeSourceWatermarkIdentity,
    current_source_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord],
    watermark_records: Mapping[NodeSourceWatermarkIdentity, NodeSourceWatermarkRecord],
) -> NodeSourceWatermarkStaleness:
    record: NodeSourceWatermarkRecord | None = watermark_records.get(record_identity)
    if record is None:
        return _unknown_classification(
            member=member,
            source_identity=source_identity,
            reason=_MISSING_FRONTIER_WATERMARK,
            current_record=current_source_records.get(source_identity),
        )
    unknown_entry: UnknownSourceWatermarkEntry
    for unknown_entry in record.payload.unknown_sources:
        if _identity_from_unknown_entry(unknown_entry) == source_identity:
            return _unknown_classification(
                member=member,
                source_identity=source_identity,
                reason=unknown_entry.reason,
                current_record=current_source_records.get(source_identity),
            )
    source_entry: SourceWatermarkEntry
    for source_entry in record.payload.sources:
        if _identity_from_entry(source_entry) == source_identity:
            return _classify_entry(
                member=member,
                source_identity=source_identity,
                entry=source_entry,
                current_source_records=current_source_records,
            )
    return _unknown_classification(
        member=member,
        source_identity=source_identity,
        reason=_MISSING_SOURCE_WATERMARK,
        current_record=current_source_records.get(source_identity),
    )


def _classify_entry(
    *,
    member: WatermarkFrontierMember,
    source_identity: SourceFreshnessIdentity,
    entry: SourceWatermarkEntry,
    current_source_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord],
) -> NodeSourceWatermarkStaleness:
    current_record: SourceFreshnessRecord | None = current_source_records.get(source_identity)
    if current_record is None:
        return _unknown_classification(
            member=member,
            source_identity=source_identity,
            reason=_MISSING_CURRENT_SOURCE_FRESHNESS,
            watermark_entry=entry,
        )
    status: WatermarkStalenessStatus = (
        WatermarkStalenessStatus.FRESH
        if entry.data_version_hash == current_record.data_version_hash
        else WatermarkStalenessStatus.STALE
    )
    return NodeSourceWatermarkStaleness(
        root_key=member.root_key,
        frontier_key=member.frontier_key,
        source_identity=source_identity,
        status=status,
        watermark_entry=entry,
        current_record=current_record,
    )


def _unknown_classification(
    *,
    member: WatermarkFrontierMember,
    source_identity: SourceFreshnessIdentity,
    reason: str,
    watermark_entry: SourceWatermarkEntry | None = None,
    current_record: SourceFreshnessRecord | None = None,
) -> NodeSourceWatermarkStaleness:
    return NodeSourceWatermarkStaleness(
        root_key=member.root_key,
        frontier_key=member.frontier_key,
        source_identity=source_identity,
        status=WatermarkStalenessStatus.UNKNOWN,
        reason=reason,
        watermark_entry=watermark_entry,
        current_record=current_record,
    )


def _identity_from_graph_key(key: WatermarkGraphKey) -> NodeSourceWatermarkIdentity:
    return NodeSourceWatermarkIdentity(node_type=key.node_type, node_name=key.node_name)


def _identity_from_entry(entry: SourceWatermarkEntry) -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name=entry.source_name,
        target_database=entry.target_database,
        target_schema=entry.target_schema,
        target_name=entry.target_name,
    )


def _identity_from_unknown_entry(entry: UnknownSourceWatermarkEntry) -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name=entry.source_name,
        target_database=entry.target_database,
        target_schema=entry.target_schema,
        target_name=entry.target_name,
    )


def _classification_sort_key(
    classification: NodeSourceWatermarkStaleness,
) -> tuple[str, str, str, str, str, str]:
    return (
        classification.root_key.node_type,
        classification.root_key.node_name,
        classification.frontier_key.node_type,
        classification.frontier_key.node_name,
        classification.source_identity.source_name,
        classification.status.value,
    )
