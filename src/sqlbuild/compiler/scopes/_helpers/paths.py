"""Project-relative path normalization implementation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import PurePath

from sqlbuild.compiler.scopes.constants import (
    CURRENT_PATH_COMPONENT,
    PARENT_PATH_COMPONENT,
    PATH_SEPARATOR,
    WINDOWS_DRIVE_PREFIX_LENGTH,
    WINDOWS_DRIVE_SEPARATOR,
)
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError


@lru_cache(maxsize=65_536)
def normalize_path(*, path: str | PurePath) -> str:
    display_path: str = str(path)
    raw: str = display_path.replace("\\", PATH_SEPARATOR)
    has_drive: bool = len(raw) >= WINDOWS_DRIVE_PREFIX_LENGTH and raw[1] == WINDOWS_DRIVE_SEPARATOR
    if not raw or raw.startswith(PATH_SEPARATOR) or has_drive:
        raise InvalidScopePathError(f"Scope path must be project-relative: {display_path}")

    components: list[str] = []
    ignored_components: frozenset[str] = frozenset({"", CURRENT_PATH_COMPONENT})
    for component in raw.split(PATH_SEPARATOR):
        if component in ignored_components:
            continue
        if component == PARENT_PATH_COMPONENT:
            if not components:
                raise InvalidScopePathError(f"Scope path escapes the project: {display_path}")
            components.pop()
            continue
        components.append(component)
    return PATH_SEPARATOR.join(components) or CURRENT_PATH_COMPONENT


def is_equal_or_descendant(*, path: str | PurePath, ancestor: str | PurePath) -> bool:
    path_parts: tuple[str, ...] = _path_parts(normalize_path(path=path))
    ancestor_path: str = normalize_path(path=ancestor)
    ancestor_parts: tuple[str, ...] = (
        () if ancestor_path == CURRENT_PATH_COMPONENT else _path_parts(ancestor_path)
    )
    return path_parts[: len(ancestor_parts)] == ancestor_parts


@lru_cache(maxsize=65_536)
def _path_parts(path: str) -> tuple[str, ...]:
    return tuple(path.split(PATH_SEPARATOR))
