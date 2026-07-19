"""Extract drill-down evidence for one package pair from a report."""

from __future__ import annotations

from scripts.dupscore.models import DupscoreReport, PairEvidenceReport


def build_pair_evidence(*, report: DupscoreReport, left: str, right: str) -> PairEvidenceReport:
    """Collect the combined rank and per-signal evidence for one package pair."""

    requested: tuple[str, str] = (left, right) if left <= right else (right, left)
    for position, entry in enumerate(report.entries, start=1):
        if entry.package_pair == requested:
            return PairEvidenceReport(
                package_pair=requested,
                combined_rank=position,
                contributions=entry.contributions,
            )
    return PairEvidenceReport(package_pair=requested, combined_rank=None, contributions=())
