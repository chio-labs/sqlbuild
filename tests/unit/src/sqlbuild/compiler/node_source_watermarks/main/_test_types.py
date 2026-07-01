from dataclasses import dataclass

from sqlbuild.compiler.node_source_watermarks.models import (
    NativeNodeSourceWatermarkInputs,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkPayload,
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
    WatermarkSourceAncestryMember,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)


@dataclass(frozen=True)
class WatermarkFrontierResolverTestCase:
    description: str
    root_keys: frozenset[WatermarkGraphKey]
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]]
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode]
    expected_members: tuple[WatermarkFrontierMember, ...]


@dataclass(frozen=True)
class WatermarkSourceAncestryResolverTestCase:
    description: str
    node_keys: frozenset[WatermarkGraphKey]
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]]
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode]
    expected_members: tuple[WatermarkSourceAncestryMember, ...]


@dataclass(frozen=True)
class NodeSourceWatermarkPayloadBuildTestCase:
    description: str
    required_source_identities: tuple[SourceFreshnessIdentity, ...]
    direct_source_records: dict[SourceFreshnessIdentity, SourceFreshnessRecord]
    inherited_payloads: tuple[NodeSourceWatermarkPayload, ...]
    expected_complete: bool
    expected_source_hashes: tuple[str, ...]
    expected_source_kinds: tuple[str, ...]
    expected_unknown_reasons: tuple[str, ...]


@dataclass(frozen=True)
class NodeSourceWatermarkExecutionContextTestCase:
    description: str
    node_identity: NodeSourceWatermarkIdentity
    source_identities_by_node: dict[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ]
    direct_source_identities_by_node: dict[
        NodeSourceWatermarkIdentity,
        tuple[SourceFreshnessIdentity, ...],
    ]
    upstream_node_identities_by_node: dict[
        NodeSourceWatermarkIdentity,
        tuple[NodeSourceWatermarkIdentity, ...],
    ]
    expected_record_written: bool
    expected_complete: bool | None
    expected_source_hashes: tuple[str, ...]
    expected_unknown_reasons: tuple[str, ...]


@dataclass(frozen=True)
class NativeNodeSourceWatermarkInputsTestCase:
    description: str
    expected_inputs: NativeNodeSourceWatermarkInputs
