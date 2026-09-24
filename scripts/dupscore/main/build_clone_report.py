"""Build the function-level clone report for the worktree."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from scripts.dupscore._helpers.clones.clustering import cluster_clone_pairs
from scripts.dupscore._helpers.clones.filters import (
    allowlist_reason,
    classify_unit_change,
    collect_changes_since,
    path_matches_any,
)
from scripts.dupscore._helpers.clones.fingerprints import fingerprint_tokens
from scripts.dupscore._helpers.clones.matching import find_clone_pairs
from scripts.dupscore._helpers.clones.sources import collect_clone_units
from scripts.dupscore._helpers.contracts.forced_overrides import find_forced_overrides
from scripts.dupscore.models import (
    CloneCluster,
    CloneOptions,
    ClonePair,
    CloneReport,
    CloneUnit,
    DupscoreConfig,
    FileChanges,
)


def build_clone_report(
    *,
    repo_root: Path,
    options: CloneOptions,
    config: DupscoreConfig,
) -> CloneReport:
    """Detect exact, renamed, and near-miss function clones and group them into clusters."""

    units: list[CloneUnit] = [
        unit
        for unit in collect_clone_units(
            repo_root=repo_root,
            languages=options.languages,
            include_tests=options.include_tests,
        )
        if len(unit.normalized) >= options.min_tokens
    ]
    fingerprints: list[frozenset[int]] = [fingerprint_tokens(unit.normalized) for unit in units]
    candidate_pairs: list[ClonePair] = find_clone_pairs(
        units=units,
        fingerprints=fingerprints,
        min_similarity=options.min_similarity,
    )
    paired: list[int] = sorted(_paired_units(candidate_pairs))
    flags: tuple[bool, ...] = find_forced_overrides(
        repo_root=repo_root,
        entries=config.contract_exemptions,
        units=[units[unit_index] for unit_index in paired],
    )
    forced: set[int] = {unit_index for unit_index, flag in zip(paired, flags, strict=True) if flag}
    retained_pairs: list[ClonePair] = [
        pair for pair in candidate_pairs if pair.left not in forced or pair.right not in forced
    ]
    pairs: list[ClonePair] = [
        pair
        for pair in retained_pairs
        if allowlist_reason(
            left_path=units[pair.left].path,
            right_path=units[pair.right].path,
            entries=config.clone_allowlist,
        )
        is None
    ]
    changes: dict[str, FileChanges] | None = (
        collect_changes_since(repo_root=repo_root, revision=options.since)
        if options.since is not None
        else None
    )

    def change_of(unit: CloneUnit) -> str | None:
        if changes is None:
            return None
        return classify_unit_change(unit=unit, changes=changes.get(unit.path))

    clusters: list[CloneCluster] = [
        cluster
        for cluster in cluster_clone_pairs(
            units=units, pairs=pairs, change_of=change_of, forced=frozenset(forced)
        )
        if _cluster_selected(cluster=cluster, options=options)
    ]
    unit_counts: Counter[str] = Counter(unit.language for unit in units)
    return CloneReport(
        since=options.since,
        unit_counts={language: unit_counts[language] for language in options.languages},
        allowlisted_pairs=len(retained_pairs) - len(pairs),
        contract_exempt_members=len(forced - _paired_units(retained_pairs)),
        clusters=tuple(clusters),
    )


def _paired_units(pairs: list[ClonePair]) -> set[int]:
    indexes: set[int] = set()
    for pair in pairs:
        indexes.update((pair.left, pair.right))
    return indexes


def _cluster_selected(*, cluster: CloneCluster, options: CloneOptions) -> bool:
    if options.since is not None and all(member.change is None for member in cluster.members):
        return False
    if options.path_globs and not any(
        path_matches_any(path=member.path, globs=options.path_globs) for member in cluster.members
    ):
        return False
    return True
