from dataclasses import dataclass

from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
    WatermarkSourceAncestryMember,
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
