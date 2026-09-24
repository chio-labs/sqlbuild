"""Report filters: lines changed since a git revision, allowlist globs, and path globs."""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from pathlib import Path

from scripts.dupscore._helpers.inputs.source_provider import run_git
from scripts.dupscore.constants import CHANGE_CHANGED, CHANGE_NEW
from scripts.dupscore.models import CloneAllowlistEntry, CloneUnit, FileChanges

_HUNK_PATTERN: re.Pattern[str] = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_TARGET_PREFIX: str = "+++ "
_TARGET_PATH_PREFIX: str = "b/"
_NULL_PATH: str = "/dev/null"
_GIT_OPTIONS: tuple[str, ...] = ("-c", "core.quotePath=false")


def collect_changes_since(*, repo_root: Path, revision: str) -> dict[str, FileChanges]:
    """Map paths to worktree lines, including untracked files, changed since ``revision``."""

    _ = run_git(repo_root=repo_root, arguments=["rev-parse", "--verify", f"{revision}^{{commit}}"])
    diff_text: str = run_git(
        repo_root=repo_root,
        arguments=[
            *_GIT_OPTIONS,
            "diff",
            "-U0",
            "--no-color",
            "--no-ext-diff",
            "--find-renames",
            "--src-prefix=a/",
            "--dst-prefix=b/",
            revision,
            "--",
        ],
    )
    changes: dict[str, FileChanges] = parse_unified_diff(diff_text)
    untracked: str = run_git(
        repo_root=repo_root,
        arguments=["ls-files", "--others", "--exclude-standard", "-z"],
    )
    for relative in untracked.split("\0"):
        if relative:
            changes[relative] = FileChanges(whole_file=True)
    return changes


def parse_unified_diff(diff_text: str) -> dict[str, FileChanges]:
    """Parse ``git diff -U0`` output into added line ranges and pure-deletion points."""

    added: dict[str, list[tuple[int, int]]] = {}
    deletions: dict[str, list[int]] = {}
    current: str | None = None
    for line in diff_text.splitlines():
        if line.startswith(_TARGET_PREFIX):
            target: str = line[len(_TARGET_PREFIX) :]
            current = None if target == _NULL_PATH else target.removeprefix(_TARGET_PATH_PREFIX)
            continue
        match: re.Match[str] | None = _HUNK_PATTERN.match(line)
        if match is None or current is None:
            continue
        start: int = int(match.group(1))
        count: int = int(match.group(2)) if match.group(2) is not None else 1
        if count == 0:
            deletions.setdefault(current, []).append(start)
        else:
            added.setdefault(current, []).append((start, start + count - 1))
    return {
        path: FileChanges(
            added_ranges=tuple(added.get(path, ())),
            deletion_points=tuple(deletions.get(path, ())),
        )
        for path in sorted(set(added) | set(deletions))
    }


def classify_unit_change(*, unit: CloneUnit, changes: FileChanges | None) -> str | None:
    """Return ``new`` when every unit line was added, ``changed`` on any overlap."""

    if changes is None:
        return None
    if changes.whole_file:
        return CHANGE_NEW
    covered: int = 0
    for range_start, range_end in changes.added_ranges:
        overlap: int = min(range_end, unit.end_line) - max(range_start, unit.start_line) + 1
        covered += max(overlap, 0)
    if covered >= unit.end_line - unit.start_line + 1:
        return CHANGE_NEW
    if covered > 0:
        return CHANGE_CHANGED
    for point in changes.deletion_points:
        if unit.start_line <= point < unit.end_line:
            return CHANGE_CHANGED
    return None


def path_matches_any(*, path: str, globs: tuple[str, ...]) -> bool:
    """Match a repo-relative POSIX path against globs where ``*`` also crosses ``/``."""

    return any(fnmatchcase(path, pattern) for pattern in globs)


def allowlist_reason(
    *,
    left_path: str,
    right_path: str,
    entries: tuple[CloneAllowlistEntry, ...],
) -> str | None:
    """Return the reason of the first entry whose globs cover both sides of a pair."""

    for entry in entries:
        if path_matches_any(path=left_path, globs=entry.paths) and path_matches_any(
            path=right_path, globs=entry.paths
        ):
            return entry.reason
    return None
