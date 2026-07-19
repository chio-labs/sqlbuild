"""Reciprocal-rank fusion of signal rankings into one combined report."""

from __future__ import annotations

from scripts.dupscore.constants import RRF_RANK_OFFSET, SIGNAL_WEIGHTS
from scripts.dupscore.models import (
    CombinedPairEntry,
    DupscoreConfig,
    DupscoreReport,
    SignalContribution,
    SignalRanking,
)


def fuse_rankings(
    *,
    rankings: tuple[SignalRanking, ...],
    config: DupscoreConfig,
    revision_label: str,
) -> DupscoreReport:
    """Fuse per-signal rankings into one deterministic combined report."""

    contributions_by_pair: dict[tuple[str, str], list[SignalContribution]] = {}
    for ranking in rankings:
        weight: float = SIGNAL_WEIGHTS.get(ranking.signal_name, 1.0)
        for rank, entry in enumerate(ranking.entries, start=1):
            points: float = weight / (RRF_RANK_OFFSET + rank)
            contribution: SignalContribution = SignalContribution(
                signal_name=ranking.signal_name,
                rank=rank,
                points=points,
                evidence=entry.evidence,
            )
            contributions_by_pair.setdefault(entry.package_pair, []).append(contribution)

    entries: list[CombinedPairEntry] = []
    for package_pair in sorted(contributions_by_pair):
        contributions: list[SignalContribution] = sorted(
            contributions_by_pair[package_pair],
            key=lambda contribution: contribution.signal_name,
        )
        total: float = sum(contribution.points for contribution in contributions)
        allowlist_reason: str | None = config.allowlisted_pairs.get(package_pair)
        entries.append(
            CombinedPairEntry(
                package_pair=package_pair,
                score=total,
                allowlisted=allowlist_reason is not None,
                allowlist_reason=allowlist_reason,
                contributions=tuple(contributions),
            )
        )
    entries.sort(key=lambda entry: (-entry.score, -len(entry.contributions), entry.package_pair))
    return DupscoreReport(
        revision_label=revision_label,
        total_pairs=len(entries),
        entries=tuple(entries),
    )


def filter_report_to_domain(*, report: DupscoreReport, domain: str | None) -> DupscoreReport:
    """Keep only entries whose pair mentions the requested domain substring."""

    if domain is None:
        return report
    matching: list[CombinedPairEntry] = []
    for entry in report.entries:
        joined_pair: str = " ".join(entry.package_pair)
        if domain in joined_pair:
            matching.append(entry)
    return DupscoreReport(
        revision_label=report.revision_label,
        total_pairs=len(matching),
        entries=tuple(matching),
    )
