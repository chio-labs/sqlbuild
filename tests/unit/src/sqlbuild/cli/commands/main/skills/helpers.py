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


def _skip_git_marker(*, repository_dir: Path) -> None:
    _ = repository_dir


def _write_git_file(*, repository_dir: Path) -> None:
    marker: Path = repository_dir / ".git"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("gitdir: elsewhere\n", encoding="utf-8")


def _write_git_directory(*, repository_dir: Path) -> None:
    (repository_dir / ".git").mkdir(parents=True)


def write_git_marker(*, repository_dir: Path, marker_is_file: bool | None) -> None:
    {None: _skip_git_marker, False: _write_git_directory, True: _write_git_file}[marker_is_file](
        repository_dir=repository_dir
    )
