"""Render dupscore reports as human-readable text or JSON."""

from __future__ import annotations

import json
from dataclasses import asdict

from scripts.dupscore.models import (
    CombinedPairEntry,
    DupscoreReport,
    PairEvidenceReport,
    ReportDelta,
)

_SIGNAL_ABBREVIATIONS: dict[str, str] = {
    "callgraph_shape": "cg",
    "state_fanin": "st",
    "dataclass_overlap": "dc",
    "same_name_symbols": "nm",
    "cochange": "cc",
}


def render_report_text(*, report: DupscoreReport, top: int) -> str:
    """Render the combined ranking as aligned text lines."""

    lines: list[str] = [
        f"dupscore report @ {report.revision_label}: {report.total_pairs} package pairs",
    ]
    for position, entry in enumerate(report.entries[:top], start=1):
        lines.append(_format_entry_line(position=position, entry=entry))
    return "\n".join(lines)


def render_report_json(*, report: DupscoreReport, top: int) -> str:
    """Render the combined ranking as deterministic JSON."""

    payload: dict[str, object] = {
        "revision_label": report.revision_label,
        "total_pairs": report.total_pairs,
        "entries": [asdict(entry) for entry in report.entries[:top]],
    }
    return json.dumps(payload, indent=1, sort_keys=True)


def render_pair_text(evidence: PairEvidenceReport) -> str:
    """Render pair drill-down evidence as text lines."""

    left, right = evidence.package_pair
    rank_label: str = (
        str(evidence.combined_rank) if evidence.combined_rank is not None else "unranked"
    )
    lines: list[str] = [f"pair {left} <-> {right} (combined rank {rank_label})"]
    for contribution in evidence.contributions:
        lines.append(f"  {contribution.signal_name} rank {contribution.rank}:")
        for item in contribution.evidence:
            lines.append(f"    {item}")
    if not evidence.contributions:
        lines.append("  no signal fired for this pair")
    return "\n".join(lines)


def render_pair_json(evidence: PairEvidenceReport) -> str:
    """Render pair drill-down evidence as deterministic JSON."""

    return json.dumps(asdict(evidence), indent=1, sort_keys=True)


def render_delta_text(delta: ReportDelta) -> str:
    """Render a two-revision comparison as text lines."""

    lines: list[str] = [f"dupscore delta {delta.base_label} -> {delta.current_label}"]
    for entry in delta.entered_top:
        lines.append("+ entered top: " + _format_entry_line(position=0, entry=entry).strip())
    for entry in delta.left_top:
        lines.append("- left top: " + _format_entry_line(position=0, entry=entry).strip())
    for item in delta.new_state_fanin_evidence:
        lines.append("+ state fan-in: " + item)
    for item in delta.new_same_name_evidence:
        lines.append("+ same-name twin: " + item)
    if len(lines) == 1:
        lines.append("no material changes")
    return "\n".join(lines)


def render_delta_json(delta: ReportDelta) -> str:
    """Render a two-revision comparison as deterministic JSON."""

    return json.dumps(asdict(delta), indent=1, sort_keys=True)


def _format_entry_line(*, position: int, entry: CombinedPairEntry) -> str:
    left, right = entry.package_pair
    signal_parts: list[str] = []
    for contribution in entry.contributions:
        abbreviation: str = _SIGNAL_ABBREVIATIONS.get(
            contribution.signal_name, contribution.signal_name
        )
        signal_parts.append(f"{abbreviation}#{contribution.rank}")
    allow_marker: str = " [allowlisted]" if entry.allowlisted else ""
    prefix: str = f"{position:3d}. " if position else ""
    return f"{prefix}{entry.score:.4f} [{','.join(signal_parts)}] {left} <-> {right}{allow_marker}"
