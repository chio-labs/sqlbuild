"""Project Python files and the strings in them that name a renamed model or column."""

from __future__ import annotations

from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.refactoring.models import ManualLocation


def python_paths(*, discovered: DiscoveredProjectInputs) -> tuple[Path, ...]:
    """Return the project Python files discovery found, sorted."""

    paths: set[Path] = set()
    paths.update(item.relative_path for item in discovered.loader_functions)
    paths.update(item.relative_path for item in discovered.task_functions)
    paths.update(item.relative_path for item in discovered.asset_functions)
    paths.update(item.relative_path for item in discovered.check_functions)
    paths.update(item.relative_path for item in discovered.hook_functions)
    paths.update(item.relative_path for item in discovered.audit_factories)
    paths.update(item.relative_path for item in discovered.python_function_files)
    paths.update(item.relative_path for item in discovered.materialization_files)
    return tuple(sorted(paths))


def string_locations(
    *,
    project_dir: Path,
    relative_path: Path,
    names: tuple[str, ...],
    reason: str,
    context: str | None,
) -> tuple[ManualLocation, ...]:
    """Return the string constants of one Python file that name a renamed model or column."""

    try:
        contents: str = (project_dir / relative_path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ()
    return tuple(
        ManualLocation(path=relative_path.as_posix(), line=line, column=column, reason=reason)
        for line, column in _native.python_string_locations(contents, list(names), context)
    )
