"""Public node source watermark source ancestry resolver entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks._helpers.source_ancestry import (
    build_watermark_source_ancestry as _build_watermark_source_ancestry,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkGraphKey,
    WatermarkGraphNode,
    WatermarkSourceAncestryMember,
)


def build_watermark_source_ancestry(
    *,
    node_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> tuple[WatermarkSourceAncestryMember, ...]:
    """Resolve raw source ancestors for graph nodes."""

    return _build_watermark_source_ancestry(
        node_keys=node_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    )
