"""Translate `sqb format` positional paths into formatter path selectors."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.lint.constants import LINT_DIRECTORY_NAMES

_FORMAT_PATH_ERROR_CODE: str = "C113"


def format_path_selectors(
    *, paths: tuple[str, ...], project_dir: Path | None, cwd: Path
) -> tuple[str, ...]:
    """Return one `path:` selector per positional path, relative to the project root."""

    project_root: Path = (project_dir if project_dir is not None else cwd).resolve()
    selectors: list[str] = []
    for raw_path in paths:
        candidate: Path = Path(raw_path)
        resolved: Path = (candidate if candidate.is_absolute() else cwd / candidate).resolve()
        if not resolved.exists():
            raise CliUserError(
                f"format path '{raw_path}' does not exist", code=_FORMAT_PATH_ERROR_CODE
            )
        if not resolved.is_relative_to(project_root):
            raise CliUserError(
                f"format path '{raw_path}' is outside the project '{project_root}'",
                code=_FORMAT_PATH_ERROR_CODE,
            )
        relative: Path = resolved.relative_to(project_root)
        if not relative.parts or relative.parts[0] not in LINT_DIRECTORY_NAMES:
            raise CliUserError(
                f"format path '{raw_path}' is not under a formatted folder",
                code=_FORMAT_PATH_ERROR_CODE,
                help="use a path under " + ", ".join(f"{name}/" for name in LINT_DIRECTORY_NAMES),
            )
        selectors.append(f"path:{relative.as_posix()}")
    return tuple(selectors)
