"""Stage refactoring edits in a scratch copy, then commit them with rollback."""

from __future__ import annotations

import os
import shutil
from pathlib import Path, PurePosixPath

from sqlbuild.compiler.refactoring._helpers.text.text_edits import apply_text_edits
from sqlbuild.compiler.refactoring.constants import (
    COPIED_PROJECT_SUFFIXES,
    HIDDEN_PREFIX,
    IGNORED_PROJECT_DIRECTORIES,
    PYCACHE_DIRECTORY,
    TEXT_ENCODING,
)
from sqlbuild.compiler.refactoring.exceptions import RefactorWriteError
from sqlbuild.compiler.refactoring.models import FileChange
from sqlbuild.lint.main.write_atomically import write_atomically


def copy_project_inputs(*, project_dir: Path, staging_dir: Path) -> int:
    """Copy every file compilation can read, skipping build output and hidden directories."""

    copied: int = 0
    root: str
    directories: list[str]
    names: list[str]
    for root, directories, names in os.walk(project_dir):
        current: Path = Path(root)
        directories[:] = sorted(
            name
            for name in directories
            if not name.startswith(HIDDEN_PREFIX)
            and not (current == project_dir and name in IGNORED_PROJECT_DIRECTORIES)
            and name != PYCACHE_DIRECTORY
        )
        name: str
        for name in names:
            source: Path = current / name
            if source.suffix not in COPIED_PROJECT_SUFFIXES or name.startswith(HIDDEN_PREFIX):
                continue
            destination: Path = staging_dir / source.relative_to(project_dir)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _ = shutil.copyfile(source, destination)
            copied += 1
    return copied


def edited_contents(
    *, originals: dict[str, str], changes: tuple[FileChange, ...]
) -> dict[str, str]:
    """Return the new text of every changed file, keyed by its final path."""

    return {
        change.path: apply_text_edits(text=originals[change.original_path], edits=change.edits)
        for change in changes
    }


def read_originals(*, project_dir: Path, changes: tuple[FileChange, ...]) -> dict[str, str]:
    """Read the current text of every file a plan changes."""

    return {
        change.original_path: (project_dir / PurePosixPath(change.original_path)).read_text(
            encoding=TEXT_ENCODING
        )
        for change in changes
    }


def write_staged_changes(
    *, staging_dir: Path, originals: dict[str, str], changes: tuple[FileChange, ...]
) -> tuple[Path, ...]:
    """Apply a plan to the scratch copy and return the written paths."""

    contents: dict[str, str] = edited_contents(originals=originals, changes=changes)
    change: FileChange
    for change in changes:
        if change.moved:
            (staging_dir / PurePosixPath(change.original_path)).unlink(missing_ok=True)
    written: list[Path] = []
    for change in changes:
        target: Path = staging_dir / PurePosixPath(change.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(contents[change.path], encoding=TEXT_ENCODING)
        written.append(target)
    prune_emptied_directories(root=staging_dir, changes=changes)
    return tuple(written)


def commit_changes(
    *, project_dir: Path, originals: dict[str, str], changes: tuple[FileChange, ...]
) -> tuple[Path, ...]:
    """Write a verified plan into the project, restoring every file if any write fails."""

    current: dict[str, str] = read_originals(project_dir=project_dir, changes=changes)
    if current != originals:
        changed: list[str] = sorted(
            path for path in originals if current.get(path) != originals[path]
        )
        raise RefactorWriteError(
            f"files changed while the refactoring ran: {', '.join(changed)}",
            help="nothing was written; run the command again",
        )
    contents: dict[str, str] = edited_contents(originals=originals, changes=changes)
    created_directories: list[Path] = []
    written: list[Path] = []
    try:
        change: FileChange
        for change in changes:
            target: Path = project_dir / PurePosixPath(change.path)
            created_directories.extend(_missing_directories(path=target.parent))
            target.parent.mkdir(parents=True, exist_ok=True)
            written.append(target)
            _write_file(
                path=target,
                contents=contents[change.path],
                mode_source=project_dir / PurePosixPath(change.original_path),
            )
        for change in changes:
            if change.moved:
                (project_dir / PurePosixPath(change.original_path)).unlink()
    except BaseException:
        _rollback(
            project_dir=project_dir,
            originals=originals,
            written=written,
            created_directories=created_directories,
        )
        raise
    prune_emptied_directories(root=project_dir, changes=changes)
    return tuple(written)


def prune_emptied_directories(*, root: Path, changes: tuple[FileChange, ...]) -> None:
    """Remove folders a move left empty, walking up to the project root."""

    change: FileChange
    for change in changes:
        if not change.moved:
            continue
        directory: Path = (root / PurePosixPath(change.original_path)).parent
        while directory != root and directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
            directory = directory.parent


def _rollback(
    *,
    project_dir: Path,
    originals: dict[str, str],
    written: list[Path],
    created_directories: list[Path],
) -> None:
    original_paths: frozenset[Path] = frozenset(
        project_dir / PurePosixPath(path) for path in originals
    )
    path: Path
    for path in written:
        if path not in original_paths:
            path.unlink(missing_ok=True)
    relative: str
    text: str
    for relative, text in originals.items():
        restored: Path = project_dir / PurePosixPath(relative)
        if restored.exists():
            write_atomically(path=restored, contents=text)
        else:
            _ = restored.write_text(text, encoding=TEXT_ENCODING)
    directory: Path
    for directory in reversed(created_directories):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()


def _write_file(*, path: Path, contents: str, mode_source: Path) -> None:
    if not path.exists():
        _ = shutil.copy(mode_source, path)
    write_atomically(path=path, contents=contents)


def _missing_directories(*, path: Path) -> list[Path]:
    missing: list[Path] = []
    current: Path = path
    while not current.exists():
        missing.append(current)
        current = current.parent
    return list(reversed(missing))
