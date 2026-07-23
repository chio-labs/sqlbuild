"""Read analyzable Python sources from the worktree or a git revision."""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.dupscore.constants import (
    EXCLUDED_MODULE_PREFIX,
    PACKAGE_DEPTH,
    PROJECT_PACKAGE,
    SOURCE_ROOT,
)
from scripts.dupscore.exceptions import DupscoreGitError

_PYTHON_SUFFIX: str = ".py"
_INIT_MODULE: str = "__init__"
_MIN_SOURCE_PATH_PARTS: int = 2


def module_name_for(relative_path: str) -> str | None:
    """Translate a repo-relative file path into an analyzable module name."""

    path: Path = Path(relative_path)
    if path.suffix != _PYTHON_SUFFIX:
        return None
    parts: tuple[str, ...] = path.with_suffix("").parts
    if (
        len(parts) < _MIN_SOURCE_PATH_PARTS
        or parts[0] != SOURCE_ROOT
        or parts[1] != PROJECT_PACKAGE
    ):
        return None
    module_parts: tuple[str, ...] = parts[1:]
    if module_parts[-1] == _INIT_MODULE:
        module_parts = module_parts[:-1]
    module: str = ".".join(module_parts)
    if module == EXCLUDED_MODULE_PREFIX or module.startswith(EXCLUDED_MODULE_PREFIX + "."):
        return None
    return module


def read_worktree_sources(repo_root: Path) -> dict[str, str]:
    """Read all analyzable module sources from the current worktree."""

    sources: dict[str, str] = {}
    package_root: Path = repo_root / SOURCE_ROOT / PROJECT_PACKAGE
    for file_path in sorted(package_root.rglob("*" + _PYTHON_SUFFIX)):
        relative: str = file_path.relative_to(repo_root).as_posix()
        module: str | None = module_name_for(relative)
        if module is None:
            continue
        sources[relative] = file_path.read_text(encoding="utf-8")
    return sources


def read_revision_sources(*, repo_root: Path, revision: str) -> dict[str, str]:
    """Read all analyzable module sources as stored at one git revision."""

    listing: str = _run_git(
        repo_root=repo_root, arguments=["ls-tree", "-r", "--name-only", revision]
    )
    sources: dict[str, str] = {}
    for relative in sorted(listing.splitlines()):
        module: str | None = module_name_for(relative)
        if module is None:
            continue
        blob_reference: str = f"{revision}:{relative}"
        sources[relative] = _run_git(repo_root=repo_root, arguments=["show", blob_reference])
    return sources


def resolve_default_base_revision(repo_root: Path) -> str:
    """Resolve the default comparison base as the merge-base with the main branch."""

    return _run_git(repo_root=repo_root, arguments=["merge-base", "main", "HEAD"]).strip()


def _run_git(*, repo_root: Path, arguments: list[str]) -> str:
    completed: subprocess.CompletedProcess[str] = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise DupscoreGitError(f"git {' '.join(arguments)} failed: {completed.stderr.strip()}")
    return completed.stdout


def package_of(module: str) -> str:
    """Reduce a module name to its aggregation package prefix."""

    parts: list[str] = module.split(".")
    return ".".join(parts[:PACKAGE_DEPTH])


def sorted_pair(*, left: str, right: str) -> tuple[str, str]:
    """Return the pair in deterministic lexicographic order."""

    if left <= right:
        return (left, right)
    return (right, left)
