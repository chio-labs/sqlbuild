"""Save and restore a project's authored files around a mutation that breaks planning."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from scripts.planner_differential.constants import COPY_IGNORED


def project_files(project_dir: Path) -> dict[str, bytes]:
    """Return every authored file's bytes, keyed by its project-relative path."""

    return {
        path.relative_to(project_dir).as_posix(): path.read_bytes()
        for path in sorted(project_dir.rglob("*"))
        if path.is_file() and not _ignored(path.relative_to(project_dir))
    }


def restore_project_files(*, project_dir: Path, files: dict[str, bytes]) -> None:
    """Rewrite the saved files and remove authored files added since they were saved."""

    for relative in project_files(project_dir):
        if relative not in files:
            (project_dir / relative).unlink()
    for relative, contents in files.items():
        path: Path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_bytes(contents)


def _ignored(relative: Path) -> bool:
    for part in relative.parts:
        if any(fnmatch.fnmatch(part, pattern) for pattern in COPY_IGNORED):
            return True
    return False
