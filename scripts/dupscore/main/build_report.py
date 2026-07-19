"""Build the fused duplication-risk report for one revision."""

from __future__ import annotations

from pathlib import Path

from scripts.dupscore._helpers.facts import extract_project_facts
from scripts.dupscore._helpers.fusion import fuse_rankings
from scripts.dupscore._helpers.signal_callgraph import score_callgraph_shape
from scripts.dupscore._helpers.signal_cochange import score_cochange
from scripts.dupscore._helpers.signal_dataclasses import score_dataclass_overlap
from scripts.dupscore._helpers.signal_same_names import score_same_name_symbols
from scripts.dupscore._helpers.signal_state_fanin import score_state_fanin
from scripts.dupscore._helpers.source_provider import read_revision_sources, read_worktree_sources
from scripts.dupscore.constants import HEAD_REVISION, WORKTREE_LABEL
from scripts.dupscore.models import DupscoreConfig, DupscoreReport, ProjectFacts, SignalRanking


def build_report(
    *,
    repo_root: Path,
    revision: str | None,
    config: DupscoreConfig,
) -> DupscoreReport:
    """Score all signals for one revision and fuse them into a ranked report."""

    sources: dict[str, str] = (
        read_worktree_sources(repo_root)
        if revision is None
        else read_revision_sources(repo_root=repo_root, revision=revision)
    )
    facts: ProjectFacts = extract_project_facts(sources)
    log_revision: str = revision if revision is not None else HEAD_REVISION
    rankings: tuple[SignalRanking, ...] = (
        score_callgraph_shape(facts),
        score_state_fanin(facts=facts, config=config),
        score_dataclass_overlap(facts),
        score_same_name_symbols(facts),
        score_cochange(facts=facts, repo_root=repo_root, revision=log_revision),
    )
    revision_label: str = revision if revision is not None else WORKTREE_LABEL
    return fuse_rankings(rankings=rankings, config=config, revision_label=revision_label)
