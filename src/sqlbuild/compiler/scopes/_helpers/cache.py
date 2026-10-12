"""Persistent canonical scope-index caching over the native fingerprint and codec."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.constants import (
    CANONICAL_AUTHORED_ROOTS,
    LOCAL_CONFIG_FILENAME,
    PROJECT_CONFIG_FILENAME,
)
from sqlbuild.compiler.frontier.main.compiler_cache_directory import compiler_cache_directory
from sqlbuild.compiler.scopes.constants import (
    GLOBAL_DECLARATION_DIRECTORIES,
    GLOBAL_NAMED_DECLARATION_DIRECTORIES,
    SCOPE_CACHE_DIRECTORY_NAME,
    SCOPE_CACHE_FILENAME,
)
from sqlbuild.compiler.scopes.models import ScopeIndex

_CONFIG_FILES: tuple[str, ...] = (
    PROJECT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    ".sqlbuildignore",
    ".gitignore",
)
_SOURCE_ROOTS: tuple[str, ...] = (
    *(Path(*parts).as_posix() for parts in CANONICAL_AUTHORED_ROOTS),
    *GLOBAL_DECLARATION_DIRECTORIES,
    *GLOBAL_NAMED_DECLARATION_DIRECTORIES,
    "python",
    "seeds",
)


def scope_index_fingerprint(*, project_dir: Path) -> str | None:
    """Hash canonical scope-relevant authored inputs, or None when they cannot be read."""

    return _native.scope_index_fingerprint(
        project_dir,
        (
            list(_CONFIG_FILES),
            list(_SOURCE_ROOTS),
            sorted(GLOBAL_DECLARATION_DIRECTORIES),
            sorted(GLOBAL_NAMED_DECLARATION_DIRECTORIES),
            _sqlbuild_version(),
        ),
    )


def read_cached_scope_index(*, project_dir: Path, fingerprint: str) -> ScopeIndex | None:
    """Read a verified index; every storage or validation fault is a cache miss."""

    return _native.read_scope_index_cache(
        compiler_cache_directory(project_dir) / SCOPE_CACHE_DIRECTORY_NAME / SCOPE_CACHE_FILENAME,
        fingerprint,
    )


def write_cached_scope_index(*, project_dir: Path, fingerprint: str, index: ScopeIndex) -> None:
    """Atomically write one complete canonical scope index, ignoring I/O faults."""

    _ = _native.write_scope_index_cache(
        (compiler_cache_directory(project_dir) / SCOPE_CACHE_DIRECTORY_NAME, SCOPE_CACHE_FILENAME),
        fingerprint,
        index,
    )


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "0+unknown"
