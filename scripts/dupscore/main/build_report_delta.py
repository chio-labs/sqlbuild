"""Compare two revision reports and describe the material differences."""

from __future__ import annotations

from scripts.dupscore.constants import SIGNAL_NAME_SAME_NAME, SIGNAL_NAME_STATE_FANIN
from scripts.dupscore.models import CombinedPairEntry, DupscoreReport, ReportDelta


def build_report_delta(*, base: DupscoreReport, current: DupscoreReport, top: int) -> ReportDelta:
    """Diff two reports: top-list membership and new high-precision evidence."""

    base_top_pairs: set[tuple[str, str]] = {entry.package_pair for entry in base.entries[:top]}
    current_top_pairs: set[tuple[str, str]] = {
        entry.package_pair for entry in current.entries[:top]
    }
    entered: tuple[CombinedPairEntry, ...] = tuple(
        entry for entry in current.entries[:top] if entry.package_pair not in base_top_pairs
    )
    left_top: tuple[CombinedPairEntry, ...] = tuple(
        entry for entry in base.entries[:top] if entry.package_pair not in current_top_pairs
    )
    new_state_evidence: tuple[str, ...] = _new_signal_evidence(
        base=base,
        current=current,
        signal_name=SIGNAL_NAME_STATE_FANIN,
    )
    new_same_name_evidence: tuple[str, ...] = _new_signal_evidence(
        base=base,
        current=current,
        signal_name=SIGNAL_NAME_SAME_NAME,
    )
    return ReportDelta(
        base_label=base.revision_label,
        current_label=current.revision_label,
        entered_top=entered,
        left_top=left_top,
        new_state_fanin_evidence=new_state_evidence,
        new_same_name_evidence=new_same_name_evidence,
    )


def _new_signal_evidence(
    *,
    base: DupscoreReport,
    current: DupscoreReport,
    signal_name: str,
) -> tuple[str, ...]:
    base_evidence: set[str] = _signal_evidence(report=base, signal_name=signal_name)
    current_evidence: set[str] = _signal_evidence(report=current, signal_name=signal_name)
    return tuple(sorted(current_evidence - base_evidence))


def _signal_evidence(*, report: DupscoreReport, signal_name: str) -> set[str]:
    evidence: set[str] = set()
    for entry in report.entries:
        for contribution in entry.contributions:
            if contribution.signal_name == signal_name and contribution.evidence:
                evidence.add(contribution.evidence[0])
    return evidence
