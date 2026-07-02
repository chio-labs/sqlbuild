"""Execution-time payload computation helpers for node source watermarks."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import datetime

from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkPayload,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkSet,
    NodeSourceWatermarkTarget,
    SourceWatermarkEntry,
    UnknownSourceWatermarkEntry,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)
from sqlbuild.spec.models.types import SourceFreshnessValueKind

_PAYLOAD_VERSION: int = 1
_UNKNOWN_MISSING_UPSTREAM_WATERMARK: str = "missing_upstream_watermark"
_UNKNOWN_MIXED_NON_ORDERABLE_WATERMARK: str = "mixed_non_orderable_watermark"


def build_node_source_watermark_payload(
    *,
    required_source_identities: Iterable[SourceFreshnessIdentity],
    direct_source_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord],
    inherited_payloads: Iterable[NodeSourceWatermarkPayload],
) -> NodeSourceWatermarkPayload:
    """Build a node payload from direct and inherited source watermark facts."""

    required_identities: tuple[SourceFreshnessIdentity, ...] = tuple(required_source_identities)
    known_by_identity: dict[SourceFreshnessIdentity, SourceWatermarkEntry] = {}
    unknown_by_identity: dict[SourceFreshnessIdentity, UnknownSourceWatermarkEntry] = {}
    direct_identity: SourceFreshnessIdentity
    direct_record: SourceFreshnessRecord
    for direct_identity, direct_record in direct_source_records.items():
        if direct_identity in required_identities:
            _merge_known_entry(
                known_by_identity=known_by_identity,
                unknown_by_identity=unknown_by_identity,
                identity=direct_identity,
                entry=_direct_entry_from_record(direct_record),
            )

    inherited_payload: NodeSourceWatermarkPayload
    for inherited_payload in inherited_payloads:
        source_entry: SourceWatermarkEntry
        for source_entry in inherited_payload.sources:
            inherited_identity: SourceFreshnessIdentity = _identity_from_entry(source_entry)
            if inherited_identity in required_identities:
                _merge_known_entry(
                    known_by_identity=known_by_identity,
                    unknown_by_identity=unknown_by_identity,
                    identity=inherited_identity,
                    entry=replace(source_entry, watermark_kind="inherited"),
                )
        unknown_entry: UnknownSourceWatermarkEntry
        for unknown_entry in inherited_payload.unknown_sources:
            unknown_identity: SourceFreshnessIdentity = _identity_from_unknown_entry(unknown_entry)
            if unknown_identity in required_identities:
                unknown_by_identity.setdefault(unknown_identity, unknown_entry)

    required_identity: SourceFreshnessIdentity
    for required_identity in required_identities:
        if (
            required_identity not in known_by_identity
            and required_identity not in unknown_by_identity
        ):
            unknown_by_identity[required_identity] = _unknown_entry(
                required_identity,
                reason=_UNKNOWN_MISSING_UPSTREAM_WATERMARK,
            )

    source_items: tuple[SourceWatermarkEntry, ...] = tuple(
        entry
        for identity, entry in sorted(
            known_by_identity.items(),
            key=lambda item: _identity_sort_key(item[0]),
        )
        if identity not in unknown_by_identity
    )
    unknown_items: tuple[UnknownSourceWatermarkEntry, ...] = tuple(
        entry
        for _, entry in sorted(
            unknown_by_identity.items(),
            key=lambda item: _identity_sort_key(item[0]),
        )
    )
    return NodeSourceWatermarkPayload(
        version=_PAYLOAD_VERSION,
        complete=not unknown_items,
        sources=source_items,
        unknown_sources=unknown_items,
    )


def build_node_source_watermark_execution_context(
    *,
    latest_watermarks: NodeSourceWatermarkSet,
    direct_source_records: Mapping[SourceFreshnessIdentity, SourceFreshnessRecord],
    direct_source_identities_by_node: Mapping[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ],
    source_identities_by_node: Mapping[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ],
    upstream_node_identities_by_node: Mapping[
        NodeSourceWatermarkIdentity,
        tuple[NodeSourceWatermarkIdentity, ...],
    ],
) -> NodeSourceWatermarkExecutionContext:
    """Initialize execution watermark context from persisted and current facts."""

    return NodeSourceWatermarkExecutionContext(
        direct_source_records=dict(direct_source_records),
        direct_source_identities_by_node=dict(direct_source_identities_by_node),
        source_identities_by_node=dict(source_identities_by_node),
        upstream_node_identities_by_node=dict(upstream_node_identities_by_node),
        payloads_by_node={
            identity: record.payload for identity, record in latest_watermarks.records.items()
        },
    )


def record_successful_node_source_watermark(
    *,
    context: NodeSourceWatermarkExecutionContext,
    node_identity: NodeSourceWatermarkIdentity,
    target: NodeSourceWatermarkTarget,
    run_id: str,
    node_version_hash: str,
    created_at: datetime,
) -> NodeSourceWatermarkRecord | None:
    """Record a successful materialized node watermark in memory and buffer it."""

    required_source_identities: tuple[SourceFreshnessIdentity, ...] = (
        context.source_identities_by_node.get(node_identity, ())
    )
    if not required_source_identities:
        return None
    upstream_payloads: tuple[NodeSourceWatermarkPayload, ...] = tuple(
        context.payloads_by_node[upstream_identity]
        for upstream_identity in context.upstream_node_identities_by_node.get(node_identity, ())
        if upstream_identity in context.payloads_by_node
    )
    direct_source_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord] = {
        identity: context.direct_source_records[identity]
        for identity in context.direct_source_identities_by_node.get(node_identity, ())
        if identity in context.direct_source_records
    }
    payload: NodeSourceWatermarkPayload = build_node_source_watermark_payload(
        required_source_identities=required_source_identities,
        direct_source_records=direct_source_records,
        inherited_payloads=upstream_payloads,
    )
    record: NodeSourceWatermarkRecord = NodeSourceWatermarkRecord(
        node_type=node_identity.node_type,
        node_name=node_identity.node_name,
        target_database=target.database,
        target_schema=target.schema,
        target_name=target.name,
        run_id=run_id,
        node_version_hash=node_version_hash,
        payload=payload,
        created_at=created_at,
    )
    context.payloads_by_node[node_identity] = payload
    context.buffered_records.append(record)
    return record


def _merge_known_entry(
    *,
    known_by_identity: dict[SourceFreshnessIdentity, SourceWatermarkEntry],
    unknown_by_identity: dict[SourceFreshnessIdentity, UnknownSourceWatermarkEntry],
    identity: SourceFreshnessIdentity,
    entry: SourceWatermarkEntry,
) -> None:
    existing_entry: SourceWatermarkEntry | None = known_by_identity.get(identity)
    if existing_entry is None:
        known_by_identity[identity] = entry
        return
    merged_entry: SourceWatermarkEntry | None = _merge_source_entries(existing_entry, entry)
    if merged_entry is None:
        unknown_by_identity[identity] = _unknown_entry(
            identity,
            reason=_UNKNOWN_MIXED_NON_ORDERABLE_WATERMARK,
        )
        known_by_identity.pop(identity, None)
        return
    known_by_identity[identity] = merged_entry


def _merge_source_entries(
    left: SourceWatermarkEntry,
    right: SourceWatermarkEntry,
) -> SourceWatermarkEntry | None:
    if left.data_version_hash == right.data_version_hash:
        return _older_observation(left, right)
    left_value_kind: SourceFreshnessValueKind | None = _value_kind(left.value_kind)
    right_value_kind: SourceFreshnessValueKind | None = _value_kind(right.value_kind)
    if left_value_kind != right_value_kind:
        return None
    if left_value_kind is SourceFreshnessValueKind.TIMESTAMP:
        return _older_timestamp_version(left, right)
    if left_value_kind is SourceFreshnessValueKind.INTEGER:
        return _older_integer_version(left, right)
    return None


def _value_kind(value: str) -> SourceFreshnessValueKind | None:
    try:
        return SourceFreshnessValueKind(value)
    except ValueError:
        return None


def _older_timestamp_version(
    left: SourceWatermarkEntry,
    right: SourceWatermarkEntry,
) -> SourceWatermarkEntry | None:
    if left.data_version is None or right.data_version is None:
        return None
    left_value: datetime = datetime.fromisoformat(left.data_version)
    right_value: datetime = datetime.fromisoformat(right.data_version)
    return left if left_value <= right_value else right


def _older_integer_version(
    left: SourceWatermarkEntry,
    right: SourceWatermarkEntry,
) -> SourceWatermarkEntry | None:
    if left.data_version is None or right.data_version is None:
        return None
    return left if int(left.data_version) <= int(right.data_version) else right


def _older_observation(
    left: SourceWatermarkEntry,
    right: SourceWatermarkEntry,
) -> SourceWatermarkEntry:
    return left if left.observed_at <= right.observed_at else right


def _direct_entry_from_record(record: SourceFreshnessRecord) -> SourceWatermarkEntry:
    return SourceWatermarkEntry(
        source_name=record.source_name,
        target_database=record.target_database,
        target_schema=record.target_schema,
        target_name=record.target_name,
        strategy=record.strategy,
        value_kind=record.value_kind,
        data_version=record.data_version,
        data_version_hash=record.data_version_hash,
        observed_at=record.observed_at,
        watermark_kind="direct",
    )


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


def _unknown_entry(
    identity: SourceFreshnessIdentity,
    *,
    reason: str,
) -> UnknownSourceWatermarkEntry:
    return UnknownSourceWatermarkEntry(
        source_name=identity.source_name,
        target_database=identity.target_database,
        target_schema=identity.target_schema,
        target_name=identity.target_name,
        reason=reason,
    )


def _identity_sort_key(identity: SourceFreshnessIdentity) -> tuple[str, str, str, str]:
    return (
        identity.source_name,
        identity.target_database or "",
        identity.target_schema or "",
        identity.target_name or "",
    )
