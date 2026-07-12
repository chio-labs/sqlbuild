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
            if classification.frontier_key.node_type != WatermarkGraphResourceKind.SOURCE.value:
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
    *,
    report: NodeSourceWatermarkStalenessReport,
    section_limit: int = _DEFAULT_SECTION_LIMIT,
) -> str:
    """Format one grouped stale-input warning block."""

    if not report.has_entries:
        return ""
    lines: list[str] = ["Stale inputs detected", ""]
    sections: tuple[tuple[str, Sequence[str]], ...] = (
        ("Affected selected models", report.affected_root_names),
        ("Stale frontier tables", report.stale_frontier_names),
        ("Changed sources", report.changed_source_names),
        ("Unknown freshness proofs", report.unknown_frontier_names),
    )
    heading: str
    values: Sequence[str]
    for heading, values in sections:
        section_lines: list[str] = _section_lines(
            heading=heading,
            values=values,
            section_limit=section_limit,
        )
        if not section_lines:
            continue
        if lines[-1] != "":
            lines.append("")
        lines.extend(section_lines)
    if lines[-1] != "":
        lines.append("")
    lines.append("  To refresh these inputs:")
    lines.append("    rebuild the upstream closure for the selected model(s)")
    return "\n".join(lines).rstrip()


def _section_lines(
    *,
    heading: str,
    values: Sequence[str],
    section_limit: int,
) -> list[str]:
    if not values:
        return []
    section_lines: list[str] = [f"  {heading}:"]
    visible_values: Sequence[str] = values[:section_limit]
    value: str
    for value in visible_values:
        section_lines.append(f"    {value}")
    hidden_count: int = len(values) - len(visible_values)
    if hidden_count > 0:
        section_lines.append(f"    +{hidden_count} more")
    return section_lines


def _unknown_frontier_label(classification: NodeSourceWatermarkStaleness) -> str:
    reason: str = classification.reason or "unknown"
    return f"{classification.frontier_key.node_name} ({reason})"
