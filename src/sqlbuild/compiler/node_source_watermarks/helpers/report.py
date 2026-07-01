"""Grouped stale-input report helpers for node source watermarks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from sqlbuild.compiler.node_source_watermarks.models import (
    NodeSourceWatermarkStaleness,
    NodeSourceWatermarkStalenessReport,
)
from sqlbuild.compiler.node_source_watermarks.types import (
    WatermarkGraphResourceKind,
    WatermarkStalenessStatus,
)

_DEFAULT_SECTION_LIMIT: int = 5


def build_node_source_watermark_staleness_report(
    *,
    classifications: Iterable[NodeSourceWatermarkStaleness],
) -> NodeSourceWatermarkStalenessReport:
    """Group stale and unknown frontier classifications for warning output."""

    affected_roots: set[str] = set()
    stale_frontiers: set[str] = set()
    changed_sources: set[str] = set()
    unknown_frontiers: set[str] = set()
    classification: NodeSourceWatermarkStaleness
    for classification in classifications:
        if classification.status == WatermarkStalenessStatus.FRESH:
            continue
        affected_roots.add(classification.root_key.node_name)
        if classification.status == WatermarkStalenessStatus.STALE:
            changed_sources.add(classification.source_identity.source_name)
            if classification.frontier_key.node_type == WatermarkGraphResourceKind.MODEL.value:
                stale_frontiers.add(classification.frontier_key.node_name)
            continue
        unknown_frontiers.add(_unknown_frontier_label(classification))
    return NodeSourceWatermarkStalenessReport(
        affected_root_names=tuple(sorted(affected_roots)),
        stale_frontier_names=tuple(sorted(stale_frontiers)),
        changed_source_names=tuple(sorted(changed_sources)),
        unknown_frontier_names=tuple(sorted(unknown_frontiers)),
    )


def format_node_source_watermark_staleness_report(
    report: NodeSourceWatermarkStalenessReport,
    *,
    section_limit: int = _DEFAULT_SECTION_LIMIT,
) -> str:
    """Format one grouped stale-input warning block."""

    if not report.has_entries:
        return ""
    lines: list[str] = ["Stale inputs detected", ""]
    _append_section(
        lines,
        heading="Affected selected models",
        values=report.affected_root_names,
        section_limit=section_limit,
    )
    _append_section(
        lines,
        heading="Stale frontier tables",
        values=report.stale_frontier_names,
        section_limit=section_limit,
    )
    _append_section(
        lines,
        heading="Changed sources",
        values=report.changed_source_names,
        section_limit=section_limit,
    )
    _append_section(
        lines,
        heading="Unknown freshness proofs",
        values=report.unknown_frontier_names,
        section_limit=section_limit,
    )
    if lines[-1] != "":
        lines.append("")
    lines.append("  To refresh these inputs:")
    lines.append("    rebuild the upstream closure for the selected model(s)")
    return "\n".join(lines).rstrip()


def _append_section(
    lines: list[str],
    *,
    heading: str,
    values: Sequence[str],
    section_limit: int,
) -> None:
    if not values:
        return
    if lines[-1] != "":
        lines.append("")
    lines.append(f"  {heading}:")
    visible_values: Sequence[str] = values[:section_limit]
    value: str
    for value in visible_values:
        lines.append(f"    {value}")
    hidden_count: int = len(values) - len(visible_values)
    if hidden_count > 0:
        lines.append(f"    +{hidden_count} more")


def _unknown_frontier_label(classification: NodeSourceWatermarkStaleness) -> str:
    reason: str = classification.reason or "unknown"
    return f"{classification.frontier_key.node_name} ({reason})"
