"""Collect authored SQL files for lint and format runs."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.lint.constants import LINT_DIRECTORY_NAMES


def collect_project_files(*, project_dir: Path) -> dict[Path, str]:
    """Return all authored SQL files in the project keyed by absolute path."""

    files: dict[Path, str] = {}
    directory_name: str
    for directory_name in LINT_DIRECTORY_NAMES:
        root: Path = project_dir / directory_name
        if not root.is_dir():
            continue
        file_path: Path
        for file_path in sorted(root.rglob("*.sql")):
            with file_path.open("r", encoding="utf-8", newline="") as handle:
                files[file_path] = handle.read()
    return files


def sort_violations(violations: list) -> tuple:
    """Return violations sorted by file path then position."""

    return tuple(sorted(violations, key=lambda item: (str(item.file_path), item.line, item.column)))
