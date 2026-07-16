"""Public node source watermark stale-input report entrypoint."""

from __future__ import annotations

from collections.abc import Iterable

from sqlbuild.compiler.node_source_watermarks._helpers.report import (
    build_node_source_watermark_staleness_report as _build_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkStaleness,
    NodeSourceWatermarkStalenessReport,
)


def build_node_source_watermark_staleness_report(
    *, classifications: Iterable[NodeSourceWatermarkStaleness]
) -> NodeSourceWatermarkStalenessReport:
    """Group stale and unknown frontier classifications for warning output."""

    return _build_node_source_watermark_staleness_report(classifications=classifications)
