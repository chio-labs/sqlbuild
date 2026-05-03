"""Filesystem helpers for type annotation convention checks."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path


def resolve_repo_root(paths: Iterable[Path]) -> Path:
    """Return the repository root for the given target paths."""

    resolved_paths: list[Path] = [path.resolve() for path in paths]
    if not resolved_paths:
        return Path.cwd().resolve()

    root: Path = resolved_paths[0]
    if root.is_file():
        root = root.parent

    while not (root / "pyproject.toml").exists() and root.parent != root:
        root = root.parent
    return root


def iter_python_files(paths: Iterable[Path]) -> list[Path]:
    """Collect Python files from the provided target paths."""

    files: set[Path] = set()
    for path in paths:
        resolved_path: Path = path.resolve()
        if resolved_path.is_file() and resolved_path.suffix == ".py":
            files.add(resolved_path)
            continue

        if resolved_path.is_dir():
            files.update(file_path.resolve() for file_path in resolved_path.rglob("*.py"))

    return sorted(files)
