from __future__ import annotations

from pathlib import Path


def existing_file_paths(*, project_dir: Path, relative_paths: tuple[Path, ...]) -> tuple[Path, ...]:
    return tuple(path for path in relative_paths if (project_dir / path).is_file())
