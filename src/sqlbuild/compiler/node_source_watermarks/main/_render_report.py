"""Public node source watermark stale-input report renderer entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.node_source_watermarks._helpers.report import (
    format_node_source_watermark_staleness_report as _format_node_source_watermark_staleness_report,
)
from sqlbuild.compiler.node_source_watermarks.models import NodeSourceWatermarkStalenessReport


def format_node_source_watermark_staleness_report(
    *,
    report: NodeSourceWatermarkStalenessReport,
    section_limit: int = 5,
) -> str:
    """Format one grouped stale-input warning block."""

    return _format_node_source_watermark_staleness_report(
        report=report,
        section_limit=section_limit,
    )
