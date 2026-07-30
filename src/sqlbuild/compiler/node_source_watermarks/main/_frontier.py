"""Public node source watermark frontier resolver entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks._helpers.frontier import (
    build_materialized_watermark_frontier as _build_materialized_watermark_frontier,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    WatermarkFrontierMember,
    WatermarkGraphKey,
    WatermarkGraphNode,
)


def build_materialized_watermark_frontier(
    *,
    root_keys: frozenset[WatermarkGraphKey],
    upstream_deps: dict[WatermarkGraphKey, tuple[WatermarkGraphKey, ...]],
    nodes: dict[WatermarkGraphKey, WatermarkGraphNode],
) -> tuple[WatermarkFrontierMember, ...]:
    """Resolve first materialized/source frontier nodes for selected roots."""

    return _build_materialized_watermark_frontier(
        root_keys=root_keys,
        upstream_deps=upstream_deps,
        nodes=nodes,
    )
