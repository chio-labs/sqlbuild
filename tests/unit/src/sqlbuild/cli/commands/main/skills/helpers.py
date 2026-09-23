from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from sqlbuild.cli.commands._helpers.skills.update import update_sqlbuild_skills
from sqlbuild.cli.output.models import SkillUpdateResult


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


def install_packaged_skill(*, project_dir: Path, target: str) -> Path:
    """Install the packaged skill for one target and return its skill directory."""

    result: SkillUpdateResult = update_sqlbuild_skills(
        project_dir=project_dir, requested_targets=(target,)
    )
    return result.written_paths[0].parent


def installed_skill_files(*, skill_dir: Path) -> dict[str, str]:
    return {
        path.relative_to(skill_dir).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(skill_dir.rglob("*.md"))
    }


def relative_markdown_links(*, text: str, base: str) -> frozenset[str]:
    """Return skill-relative targets of non-URL Markdown links in one skill file."""

    return frozenset(
        str(PurePosixPath(base, link)) for link in re.findall(r"\]\(((?!https?:)[^)#\s]+)", text)
    )


def mentioned_sqb_commands(*, text: str) -> frozenset[str]:
    return frozenset(re.findall(r"(?:^|[`\s(])sqb ([a-z][a-z-]*)", text, flags=re.MULTILINE))
