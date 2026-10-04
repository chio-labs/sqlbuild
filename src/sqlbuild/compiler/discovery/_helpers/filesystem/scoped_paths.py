"""Project-relative path facts shared by filesystem discovery."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sqlbuild.compiler.discovery.constants import (
    CANONICAL_AUTHORED_ROOTS,
    SQL_TESTS_OWNERSHIP_ROOT,
)
from sqlbuild.compiler.scopes.constants import (
    DECLARATION_GROUP_DIRECTORY,
    SCOPED_DECLARATION_DIRECTORIES,
)
from sqlbuild.compiler.scopes.types import DeclarationKind

_MACRO_TEST_DIRECTORY: str = f"{DeclarationKind.MACRO.value}s"
_SQL_FILE_SUFFIX: str = ".sql"
_SQL_TEST_ROOT_COMPONENTS: tuple[str, ...] = Path(SQL_TESTS_OWNERSHIP_ROOT).parts


def project_relative_path(*, path: Path, project_dir: Path) -> Path:
    """Return path.relative_to(project_dir) without pathlib's per-parent comparison scan."""

    root_parts: tuple[str, ...] = project_dir.parts
    path_parts: tuple[str, ...] = path.parts
    if (
        path.is_absolute() is not project_dir.is_absolute()
        or path_parts[: len(root_parts)] != root_parts
    ):
        return path.relative_to(project_dir)
    return path.with_segments(*path_parts[len(root_parts) :])


def is_in_scoped_declaration_tree(*, file_path: Path, project_dir: Path) -> bool:
    """Return whether a file lives inside a scoped declaration tree rather than a resource tree."""

    return _is_scoped_declaration_directory(
        directory=file_path.parent,
        project_dir=project_dir,
        sql_file=file_path.suffix == _SQL_FILE_SUFFIX,
    )


@lru_cache(maxsize=8192)
def _is_scoped_declaration_directory(*, directory: Path, project_dir: Path, sql_file: bool) -> bool:
    """Classify a file's directory once; every file in it shares the same scoped-tree answer."""

    directory_parts: tuple[str, ...] = project_relative_path(
        path=directory, project_dir=project_dir
    ).parts
    root_components: tuple[str, ...]
    for root_components in CANONICAL_AUTHORED_ROOTS:
        if directory_parts[: len(root_components)] != root_components:
            continue
        scoped_components: tuple[str, ...] = directory_parts[len(root_components) :]
        if (
            root_components == _SQL_TEST_ROOT_COMPONENTS
            and sql_file
            and scoped_components[:1] == (_MACRO_TEST_DIRECTORY,)
        ):
            return False
        return any(
            component == DECLARATION_GROUP_DIRECTORY or component in SCOPED_DECLARATION_DIRECTORIES
            for component in scoped_components
        )
    return False
