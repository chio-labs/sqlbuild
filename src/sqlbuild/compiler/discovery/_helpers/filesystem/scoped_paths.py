"""Project-relative path facts shared by filesystem discovery."""

from __future__ import annotations

from pathlib import Path


def project_relative_path(*, path: Path, project_dir: Path) -> Path:
    """Return path.relative_to(project_dir) without pathlib's per-parent comparison scan."""

    root_parts: tuple[str, ...] = project_dir.parts
    path_parts: tuple[str, ...] = path.parts
    if (
        path.is_absolute() is not project_dir.is_absolute()
        or path_parts[: len(root_parts)] != root_parts
    ):
        return path.relative_to(project_dir)
    return path.with_segments(*path_parts[len(root_parts) :])
