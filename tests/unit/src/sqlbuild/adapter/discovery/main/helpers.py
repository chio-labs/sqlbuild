from __future__ import annotations

from pathlib import Path


def write_project_files(*, project_dir: Path, files: dict[str, str]) -> None:
    relative_path: str
    contents: str
    for relative_path, contents in files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")
