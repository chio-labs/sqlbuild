"""Filesystem helpers for structure convention checks."""

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


def iter_scoped_python_files(repo_root: Path, *, paths: Iterable[Path]) -> list[Path]:
    """Collect Python files within the structure-checker scope."""

    files: set[Path] = set()
    for path in paths:
        resolved: Path = path.resolve()
        if resolved.is_file() and resolved.suffix == ".py":
            if is_scoped_python_file(repo_root, file_path=resolved):
                files.add(resolved)
            continue

        if resolved.is_dir():
            for file_path in resolved.rglob("*.py"):
                resolved_file_path: Path = file_path.resolve()
                if is_scoped_python_file(repo_root, file_path=resolved_file_path):
                    files.add(resolved_file_path)

    return sorted(files)


def is_scoped_python_file(repo_root: Path, *, file_path: Path) -> bool:
    """Return whether the file is inside the checker's enforced scope."""

    try:
        relative_parts: tuple[str, ...] = file_path.resolve().relative_to(repo_root.resolve()).parts
    except ValueError:
        return False

    if not relative_parts:
        return False

    if relative_parts[0] == "scripts":
        return True

    return (
        len(relative_parts) >= 2 and relative_parts[0] == "src" and relative_parts[1] == "sqlbuild"
    )


def module_name_for_file(repo_root: Path, *, file_path: Path) -> str:
    """Convert a file path into its importable module path."""

    relative_path: Path = file_path.resolve().relative_to(repo_root.resolve())
    return ".".join(relative_path.with_suffix("").parts)
