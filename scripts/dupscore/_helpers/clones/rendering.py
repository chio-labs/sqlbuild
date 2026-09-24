"""Render clone reports as concise text or deterministic JSON."""

from __future__ import annotations

import json
from dataclasses import asdict

from scripts.dupscore.constants import CLONE_TEXT_MAX_MEMBERS
from scripts.dupscore.models import CloneCluster, CloneMember, CloneReport

_INDENT: str = "     "


def render_clone_text(*, report: CloneReport, top: int) -> str:
    """Render the ranked clusters with one line per member."""

    counts: str = ", ".join(
        f"{language} {count} units" for language, count in report.unit_counts.items()
    )
    scope: str = f" changed since {report.since}" if report.since is not None else ""
    lines: list[str] = [
        f"dupscore clones{scope}: {len(report.clusters)} clusters "
        f"({counts}; {report.allowlisted_pairs} allowlisted pairs hidden; "
        f"{report.contract_exempt_members} contract-exempt members hidden)"
    ]
    for position, cluster in enumerate(report.clusters[:top], start=1):
        lines.append(f"{position:3d}. {_cluster_heading(cluster)}")
        shown: tuple[CloneMember, ...] = cluster.members[:CLONE_TEXT_MAX_MEMBERS]
        lines.extend(_INDENT + _member_line(member) for member in shown)
        hidden: int = len(cluster.members) - len(shown)
        if hidden:
            lines.append(f"{_INDENT}... {hidden} more members (see --json)")
    if not report.clusters:
        lines.append("no clones found")
    elif len(report.clusters) > top:
        lines.append(f"... {len(report.clusters) - top} more clusters (use --top)")
    return "\n".join(lines)


def render_clone_json(*, report: CloneReport, top: int) -> str:
    """Render the ranked clusters as deterministic JSON."""

    payload: dict[str, object] = {
        "since": report.since,
        "unit_counts": report.unit_counts,
        "allowlisted_pairs": report.allowlisted_pairs,
        "contract_exempt_members": report.contract_exempt_members,
        "total_clusters": len(report.clusters),
        "clusters": [
            {"rank": position, **asdict(cluster)}
            for position, cluster in enumerate(report.clusters[:top], start=1)
        ],
    }
    return json.dumps(payload, indent=1, sort_keys=True)


def _cluster_heading(cluster: CloneCluster) -> str:
    lowest: str = f"{cluster.similarity_min:.2f}"
    highest: str = f"{cluster.similarity_max:.2f}"
    similarity: str = highest if lowest == highest else f"{lowest}-{highest}"
    return (
        f"{cluster.category} sim {similarity}, ~{cluster.duplicated_tokens} duplicated tokens, "
        f"{len(cluster.members)} members"
    )


def _member_line(member: CloneMember) -> str:
    change: str = f" [{member.change}]" if member.change is not None else ""
    return (
        f"{member.path}:{member.start_line}-{member.end_line} {member.name} "
        f"({member.tokens} tokens){change}"
    )
