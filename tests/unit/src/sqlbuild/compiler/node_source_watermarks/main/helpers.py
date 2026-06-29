from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkGraphKey,
    WatermarkGraphNode,
)
from sqlbuild.compiler.node_source_watermarks.types import WatermarkGraphResourceKind


def graph_key(name: str, *, node_type: str = "model") -> WatermarkGraphKey:
    return WatermarkGraphKey(node_type=node_type, node_name=name)


def model_node(name: str, *, materialized: bool) -> WatermarkGraphNode:
    key: WatermarkGraphKey = graph_key(name)
    return WatermarkGraphNode(
        key=key,
        resource_kind=WatermarkGraphResourceKind.MODEL,
        materialized=materialized,
    )


def source_node(name: str) -> WatermarkGraphNode:
    key: WatermarkGraphKey = graph_key(name, node_type="source")
    return WatermarkGraphNode(
        key=key,
        resource_kind=WatermarkGraphResourceKind.SOURCE,
        materialized=False,
    )


def nodes_by_key(*nodes: WatermarkGraphNode) -> dict[WatermarkGraphKey, WatermarkGraphNode]:
    return {node.key: node for node in nodes}
