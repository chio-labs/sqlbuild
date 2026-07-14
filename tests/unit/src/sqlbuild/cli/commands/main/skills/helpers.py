from __future__ import annotations

from pathlib import Path


def write_project_files(*, project_dir: Path, files: dict[Path, str]) -> None:
    relative_path: Path
    contents: str
    for relative_path, contents in files.items():
        file_path: Path = project_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(contents, encoding="utf-8")


def read_relative_file(*, project_dir: Path, relative_path: Path) -> str:
    return (project_dir / relative_path).read_text(encoding="utf-8")


def prepare_skill_update_project(
    *, project_dir: Path, project_config: str | None, existing_files: dict[Path, str]
) -> None:
    project_files: dict[Path, str] = {
        False: {},
        True: {Path("sqlbuild_project.toml"): str(project_config)},
    }[project_config is not None]
    write_project_files(project_dir=project_dir, files=project_files)
    write_project_files(project_dir=project_dir, files=existing_files)
