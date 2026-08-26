"""Project-relative path normalization implementation."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes.constants import (
    CURRENT_PATH_COMPONENT,
    PARENT_PATH_COMPONENT,
    PATH_SEPARATOR,
    WINDOWS_DRIVE_PREFIX_LENGTH,
    WINDOWS_DRIVE_SEPARATOR,
)
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError


def normalize_path(*, path: str | PurePath) -> str:
    raw: str = str(path).replace("\\", PATH_SEPARATOR)
    has_drive: bool = len(raw) >= WINDOWS_DRIVE_PREFIX_LENGTH and raw[1] == WINDOWS_DRIVE_SEPARATOR
    if not raw or raw.startswith(PATH_SEPARATOR) or has_drive:
        raise InvalidScopePathError(f"Scope path must be project-relative: {path!s}")

    components: list[str] = []
    ignored_components: frozenset[str] = frozenset({"", CURRENT_PATH_COMPONENT})
    for component in raw.split(PATH_SEPARATOR):
        if component in ignored_components:
            continue
        if component == PARENT_PATH_COMPONENT:
            if not components:
                raise InvalidScopePathError(f"Scope path escapes the project: {path!s}")
            components.pop()
            continue
        components.append(component)
    return PATH_SEPARATOR.join(components) or CURRENT_PATH_COMPONENT


def is_equal_or_descendant(*, path: str | PurePath, ancestor: str | PurePath) -> bool:
    path_parts: list[str] = normalize_path(path=path).split(PATH_SEPARATOR)
    ancestor_path: str = normalize_path(path=ancestor)
    ancestor_parts: list[str] = (
        [] if ancestor_path == CURRENT_PATH_COMPONENT else ancestor_path.split(PATH_SEPARATOR)
    )
    return path_parts[: len(ancestor_parts)] == ancestor_parts
