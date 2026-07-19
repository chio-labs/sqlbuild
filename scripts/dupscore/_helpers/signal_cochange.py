"""Signal: git co-change coupling between packages without import coupling."""

from __future__ import annotations

import subprocess
from itertools import combinations
from pathlib import Path

from scripts.dupscore._helpers.source_provider import module_name_for, package_of
from scripts.dupscore.constants import (
    MAX_FILES_PER_COMMIT,
    MIN_COCHANGES,
    SIGNAL_NAME_COCHANGE,
)
from scripts.dupscore.exceptions import DupscoreGitError
from scripts.dupscore.models import ProjectFacts, SignalPairScore, SignalRanking

_COMMIT_SENTINEL: str = "\x01"
_MIN_FILES_PER_COMMIT: int = 2


def score_cochange(*, facts: ProjectFacts, repo_root: Path, revision: str) -> SignalRanking:
    """Rank cross-package module pairs that co-change without import coupling."""

    commits: list[list[str]] = _read_commit_modules(repo_root=repo_root, revision=revision)
    live_modules: set[str] = {module_facts.module for module_facts in facts.modules}
    import_edges: set[tuple[str, str]] = _module_import_edges(facts)

    pair_counts: dict[tuple[str, str], int] = {}
    change_counts: dict[str, int] = {}
    for commit_modules in commits:
        unique_modules: list[str] = sorted(set(commit_modules))
        for module in unique_modules:
            change_counts[module] = change_counts.get(module, 0) + 1
        if not (_MIN_FILES_PER_COMMIT <= len(unique_modules) <= MAX_FILES_PER_COMMIT):
            continue
        for left, right in combinations(unique_modules, 2):
            pair_counts[(left, right)] = pair_counts.get((left, right), 0) + 1

    best_per_pair: dict[tuple[str, str], SignalPairScore] = {}
    for (left, right), count in sorted(pair_counts.items()):
        if count < MIN_COCHANGES:
            continue
        if left not in live_modules or right not in live_modules:
            continue
        if (left, right) in import_edges or (right, left) in import_edges:
            continue
        left_package: str = package_of(left)
        right_package: str = package_of(right)
        if left_package == right_package:
            continue
        confidence: float = count / min(change_counts[left], change_counts[right])
        score: float = count * confidence
        cochange_summary: str = f"co-changed in {count} commits (confidence {confidence:.2f})"
        evidence: tuple[str, ...] = (f"modules {left} <-> {right} {cochange_summary}",)
        package_pair: tuple[str, str] = (
            (left_package, right_package)
            if left_package <= right_package
            else (right_package, left_package)
        )
        candidate: SignalPairScore = SignalPairScore(
            package_pair=package_pair, score=score, evidence=evidence
        )
        existing: SignalPairScore | None = best_per_pair.get(package_pair)
        if existing is None or (-candidate.score, candidate.evidence) < (
            -existing.score,
            existing.evidence,
        ):
            best_per_pair[package_pair] = candidate

    ordered: list[SignalPairScore] = sorted(
        best_per_pair.values(),
        key=lambda entry: (-entry.score, entry.package_pair, entry.evidence),
    )
    return SignalRanking(signal_name=SIGNAL_NAME_COCHANGE, entries=tuple(ordered))


def _read_commit_modules(*, repo_root: Path, revision: str) -> list[list[str]]:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", "log", f"--format={_COMMIT_SENTINEL}%H", "--name-only", revision],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise DupscoreGitError(f"git log for {revision} failed: {completed.stderr.strip()}")
    commits: list[list[str]] = []
    current: list[str] = []
    for line in completed.stdout.splitlines():
        if line.startswith(_COMMIT_SENTINEL):
            if current:
                commits.append(current)
            current = []
            continue
        stripped: str = line.strip()
        if not stripped:
            continue
        module: str | None = module_name_for(stripped)
        if module is not None:
            current.append(module)
    if current:
        commits.append(current)
    return commits


def _module_import_edges(facts: ProjectFacts) -> set[tuple[str, str]]:
    live_modules: set[str] = {module_facts.module for module_facts in facts.modules}
    edges: set[tuple[str, str]] = set()
    for module_facts in facts.modules:
        for target in module_facts.imported_modules:
            if not target.startswith("sqlbuild"):
                continue
            candidate: str = target
            while candidate and candidate not in live_modules:
                candidate = candidate.rpartition(".")[0]
            if candidate:
                edges.add((module_facts.module, candidate))
    return edges
