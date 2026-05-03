"""Filesystem helpers for test convention checks."""

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
        resolved: Path = path.resolve()
        if resolved.is_file() and resolved.suffix == ".py":
            files.add(resolved)
            continue

        if resolved.is_dir():
            files.update(file_path.resolve() for file_path in resolved.rglob("*.py"))

    return sorted(files)


def discover_test_directories(python_files: Iterable[Path]) -> list[Path]:
    """Return directories that contain pytest-style test modules."""

    directories: set[Path] = {
        file_path.parent
        for file_path in python_files
        if file_path.name.startswith("test_") and file_path.suffix == ".py"
    }
    return sorted(directories)


def module_name_for_file(repo_root: Path, file_path: Path) -> str:
    """Convert a file path into its importable module path."""

    relative_path: Path = file_path.resolve().relative_to(repo_root.resolve())
    return ".".join(relative_path.with_suffix("").parts)
