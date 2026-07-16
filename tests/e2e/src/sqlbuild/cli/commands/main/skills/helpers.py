from __future__ import annotations

from pathlib import Path


def existing_file_paths(*, project_dir: Path, relative_paths: tuple[Path, ...]) -> tuple[Path, ...]:
    existing_paths: list[Path] = []
    for path in relative_paths:
        existing_paths.extend((path,) * int((project_dir / path).is_file()))
    return tuple(existing_paths)


def write_existing_skill_file(*, project_dir: Path, relative_path: Path, contents: str) -> None:
    skill_file_path: Path = project_dir / relative_path
    skill_file_path.parent.mkdir(parents=True, exist_ok=True)
    skill_file_path.write_text(contents, encoding="utf-8")
