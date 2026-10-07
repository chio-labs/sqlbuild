"""Shared decoding of the plain-data payloads native discovery returns."""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.exceptions import DiscoveryError, ModelSqlParseError
from sqlbuild.compiler.discovery.types import (
    DirectorySnapshotEntry,
    NativeListing,
    NativeLocation,
)
from sqlbuild.spec.contracts.models import SourceLocation

_DISPLAY_PROBE: str = "_"
_WINDOWS_OS_NAME: str = "nt"
_PATH_ENCODING: str = "utf-8"
_FAILURE_CLASSES: dict[str, type[DiscoveryError]] = {"model_sql": ModelSqlParseError}


def native_display_prefix(project_dir: Path) -> str:
    """Return the text `str(project_dir / name)` prints before `name`."""

    return str(project_dir / _DISPLAY_PROBE)[: -len(_DISPLAY_PROBE)]


def native_failure(payload: tuple[object, ...]) -> DiscoveryError:
    """Build the discovery error a native failure payload describes."""

    _tag, kind, message, help_text = payload
    error_class: type[DiscoveryError] = _FAILURE_CLASSES[str(kind)]
    return error_class(str(message), help=None if help_text is None else str(help_text))


def native_locations(
    *, locations: list[NativeLocation], relative_path: Path
) -> dict[str, SourceLocation]:
    """Build authored locations; a repeated name keeps its first position and last value."""

    return {
        name: SourceLocation(
            path=relative_path,
            line=line,
            column=column,
            end_line=end_line,
            end_column=end_column,
        )
        for name, line, column, end_line, end_column in locations
    }


def native_discovery_supported(*, project_dir: Path, display_prefix: str) -> bool:
    """Whether native discovery reproduces Python here: same Unicode data, UTF-8 paths, POSIX."""

    return (
        os.name != _WINDOWS_OS_NAME
        and unicodedata.unidata_version == _native.PYTHON_ALNUM_UNICODE_VERSION
        and _is_utf8_text(str(project_dir))
        and _is_utf8_text(display_prefix)
    )


def seed_snapshot_listings(*, project_dir: Path, listings: list[NativeListing]) -> None:
    """Share the native walk's listings with the pass's Python directory snapshot."""

    DirectorySnapshot.current(project_dir=project_dir).seed_listings(
        {project_dir / directory: _snapshot_entries(entries) for directory, entries in listings}
    )


def _snapshot_entries(
    entries: list[tuple[str, bool, bool]],
) -> tuple[DirectorySnapshotEntry, ...]:
    return tuple(
        DirectorySnapshotEntry(name=name, is_dir=is_dir, is_walkable_dir=walkable)
        for name, is_dir, walkable in entries
    )


def _is_utf8_text(text: str) -> bool:
    try:
        _ = text.encode(_PATH_ENCODING)
    except UnicodeEncodeError:
        return False
    return True
