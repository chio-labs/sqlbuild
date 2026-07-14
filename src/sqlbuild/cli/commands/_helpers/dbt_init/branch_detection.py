"""Best-effort production default branch detection for dbt reuse setup."""

from __future__ import annotations

import subprocess
from pathlib import Path

_FALLBACK_DEFAULT_BRANCH: str = "main"
_COMMON_DEFAULT_BRANCHES: tuple[str, ...] = ("main", "master")


def detect_default_production_git_ref(*, git_probe_dir: Path) -> str:
    """Detect a sensible production git ref, defaulting to 'main' when unknown."""

    git_root: str | None = _git_text(
        args=("-C", str(git_probe_dir), "rev-parse", "--show-toplevel")
    )
    if git_root is None:
        return _FALLBACK_DEFAULT_BRANCH
    remote_head: str | None = _remote_head_branch(git_root=git_root)
    if remote_head is not None:
        return remote_head
    existing_common: str | None = _first_existing_common_branch(git_root=git_root)
    if existing_common is not None:
        return existing_common
    current_branch: str | None = _git_text(args=("-C", git_root, "branch", "--show-current"))
    if current_branch:
        return current_branch
    return _FALLBACK_DEFAULT_BRANCH


def _remote_head_branch(*, git_root: str) -> str | None:
    head_ref: str | None = _git_text(
        args=("-C", git_root, "symbolic-ref", "refs/remotes/origin/HEAD")
    )
    if head_ref is None:
        return None
    branch: str = head_ref.removeprefix("refs/remotes/origin/")
    if not branch or branch == head_ref:
        return None
    return branch


def _first_existing_common_branch(*, git_root: str) -> str | None:
    branch: str
    for branch in _COMMON_DEFAULT_BRANCHES:
        verified: str | None = _git_text(
            args=("-C", git_root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
        )
        if verified is not None:
            return branch
    return None


def _git_text(*, args: tuple[str, ...]) -> str | None:
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            ("git", *args),
            capture_output=True,
            check=False,
            text=True,
        )
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return None
    output: str = result.stdout.strip()
    return output or None
