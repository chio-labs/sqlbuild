"""Public node source watermark execution context entrypoint."""

from __future__ import annotations

from collections.abc import Mapping

from sqlbuild.compiler.node_source_watermarks.helpers.context import (
    build_node_source_watermark_execution_context as _build_node_source_watermark_execution_context,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkSet,
)
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
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

    return _build_node_source_watermark_execution_context(
        latest_watermarks=latest_watermarks,
        direct_source_records=direct_source_records,
        direct_source_identities_by_node=direct_source_identities_by_node,
        source_identities_by_node=source_identities_by_node,
        upstream_node_identities_by_node=upstream_node_identities_by_node,
    )
