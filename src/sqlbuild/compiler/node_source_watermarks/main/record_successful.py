"""Public successful node source watermark recording entrypoint."""

from __future__ import annotations

from datetime import datetime

from sqlbuild.compiler.node_source_watermarks._helpers.context import (
    record_successful_node_source_watermark as _record_successful_node_source_watermark,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkExecutionContext,
    NodeSourceWatermarkIdentity,
    NodeSourceWatermarkRecord,
    NodeSourceWatermarkTarget,
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

    return _record_successful_node_source_watermark(
        context=context,
        node_identity=node_identity,
        target=target,
        run_id=run_id,
        node_version_hash=node_version_hash,
        created_at=created_at,
    )
