"""Validation for the supported SQLBuild project Python layout."""

from __future__ import annotations

import os
from pathlib import Path

from sqlbuild.compiler.discovery.constants import (
    CANONICAL_AUTHORED_ROOTS,
    LANGUAGE_PYTHON_ROOT_PART_COUNT,
    PYTHON_CACHE_DIRECTORY_NAME,
)
from sqlbuild.compiler.discovery.exceptions import ProjectPythonPathError
from sqlbuild.compiler.scopes.constants import (
    GLOBAL_DECLARATION_DIRECTORIES,
    INHERITED_DECLARATION_DIRECTORIES,
    LOCAL_DECLARATION_DIRECTORIES,
)

_DIRECT_PYTHON_ROOTS: frozenset[str] = frozenset(
    {
        "adapters",
        "assets",
        "checks",
        "dagster",
        "factories",
        "kata",
        "loaders",
        "libs",
        "materializations",
        "providers",
        "rivers_pipeline",
        "sinks",
        "tasks",
    }
)
_LANGUAGE_PYTHON_ROOTS: frozenset[tuple[str, str]] = frozenset(
    {("functions", "python"), ("hooks", "python")}
)
_IGNORED_ROOTS: frozenset[str] = frozenset({"logs", "target", "venv"})
_LEGACY_DIAGNOSTIC_ROOTS: frozenset[str] = frozenset({"event_exporters"})
_SUPPORTED_ROOT_FILES: frozenset[Path] = frozenset({Path("adapter.py"), Path("definitions.py")})
_SCOPED_DECLARATION_DIRECTORIES: frozenset[str] = (
    INHERITED_DECLARATION_DIRECTORIES | LOCAL_DECLARATION_DIRECTORIES
)


def validate_project_python_paths(*, project_dir: Path) -> None:
    """Reject project Python outside documented executable roots."""

    unsupported: tuple[Path, ...] = _unsupported_python_paths(project_dir=project_dir)
    if not unsupported:
        return
    rendered_paths: str = ", ".join(str(path) for path in unsupported)
    raise ProjectPythonPathError(
        f"Unsupported project Python path(s): {rendered_paths}",
        help=(
            "Move project Python under a documented resource, library, or integration path. "
            "Factory support modules, including factories/**/_helpers.py, are allowed."
        ),
    )


def _unsupported_python_paths(*, project_dir: Path) -> tuple[Path, ...]:
    unsupported: list[Path] = []
    for file_path in _project_python_files(project_dir=project_dir):
        if _is_supported(file_path=file_path, project_dir=project_dir):
            continue
        unsupported.append(file_path.relative_to(project_dir))
    return tuple(unsupported)


def _project_python_files(*, project_dir: Path) -> tuple[Path, ...]:
    files: list[Path] = []
    for root, directories, filenames in os.walk(project_dir):
        root_path: Path = Path(root)
        directories[:] = [
            name
            for name in directories
            if not name.startswith(".")
            and name != PYTHON_CACHE_DIRECTORY_NAME
            and not (root_path == project_dir and name in _IGNORED_ROOTS)
        ]
        files.extend(root_path / name for name in filenames if name.endswith(".py"))
    return tuple(sorted(files))


def _is_supported(*, file_path: Path, project_dir: Path) -> bool:
    relative_path: Path = file_path.relative_to(project_dir)
    parts: tuple[str, ...] = relative_path.parts
    if relative_path in _SUPPORTED_ROOT_FILES:
        return True
    if (
        parts[0] in _DIRECT_PYTHON_ROOTS
        or parts[0] in GLOBAL_DECLARATION_DIRECTORIES
        or parts[0] in _LEGACY_DIAGNOSTIC_ROOTS
    ):
        return True
    if (
        len(parts) >= LANGUAGE_PYTHON_ROOT_PART_COUNT
        and parts[:LANGUAGE_PYTHON_ROOT_PART_COUNT] in _LANGUAGE_PYTHON_ROOTS
    ):
        return True
    return _is_scoped_declaration_path(parts)


def _is_scoped_declaration_path(parts: tuple[str, ...]) -> bool:
    for root_parts in CANONICAL_AUTHORED_ROOTS:
        if parts[: len(root_parts)] != root_parts:
            continue
        return any(part in _SCOPED_DECLARATION_DIRECTORIES for part in parts[len(root_parts) : -1])
    return False
