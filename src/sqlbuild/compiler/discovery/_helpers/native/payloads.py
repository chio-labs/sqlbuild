"""Shared decoding of the plain-data payloads native discovery returns."""

from __future__ import annotations

import os
import sys
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.exceptions import (
    DeclarationParseError,
    DiscoveryError,
    ModelSqlParseError,
    SqlScenarioParseError,
    SqlTestParseError,
)
from sqlbuild.compiler.discovery.models import DiscoveryFileFault
from sqlbuild.compiler.discovery.types import (
    DirectorySnapshotEntry,
    NativeListing,
    NativeLocation,
)
from sqlbuild.spec.contracts.models import SourceLocation

_DISPLAY_PROBE: str = "_"
_WINDOWS_OS_NAME: str = "nt"
_PATH_ENCODING: str = "utf-8"
_NATIVE_TREE_MEMO_KEY: str = "native_project_tree"
_FAILURE_CLASSES: dict[str, type[DiscoveryError]] = {
    "model_sql": ModelSqlParseError,
    "declaration": DeclarationParseError,
    "sql_test": SqlTestParseError,
    "sql_scenario": SqlScenarioParseError,
}


def native_display_prefix(project_dir: Path) -> str:
    """Return the text `str(project_dir / name)` prints before `name`."""

    return str(project_dir / _DISPLAY_PROBE)[: -len(_DISPLAY_PROBE)]


def native_failure(payload: tuple[object, ...]) -> DiscoveryError:
    """Build the discovery error a native failure payload describes."""

    _tag, kind, message, help_text = payload
    error_class: type[DiscoveryError] = _FAILURE_CLASSES[str(kind)]
    return error_class(str(message), help=None if help_text is None else str(help_text))


def materialise_native_files[RecordT](
    *,
    project_dir: Path,
    files: Iterable[tuple[Path, tuple[object, ...]]],
    build: Callable[[Path, tuple[object, ...]], RecordT],
    on_fault: Callable[[DiscoveryFileFault], None] | None,
) -> tuple[RecordT, ...]:
    """Build each native file payload, reporting and skipping a failing file when asked."""

    records: list[RecordT] = []
    for relative_path, payload in files:
        try:
            records.append(build(relative_path, payload))
        except (OSError, UnicodeError, ValueError, SyntaxError) as error:
            if on_fault is None:
                raise
            on_fault(
                DiscoveryFileFault(
                    path=relative_path, message=str(error).replace(str(project_dir), ".")
                )
            )
    return tuple(records)


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


def native_text_runtime() -> dict[str, object]:
    """Return the request fields naming the Python whose string semantics native reproduces."""

    return {"python_version": _python_version(), "unicode_version": unicodedata.unidata_version}


def native_discovery_supported(*, project_dir: Path, display_prefix: str) -> bool:
    """Whether native discovery reproduces Python here: known Python, UTF-8 paths, POSIX."""

    return (
        os.name != _WINDOWS_OS_NAME
        and native_text_supported()
        and _is_utf8_text(str(project_dir))
        and _is_utf8_text(display_prefix)
    )


def native_text_supported() -> bool:
    """Whether native parsing reproduces the string semantics of the running Python."""

    return _native.native_text_supported(_python_version(), unicodedata.unidata_version)


def native_project_tree(project_dir: Path) -> _native.NativeProjectTree:
    """Return the native listings shared by every native call of this discovery pass."""

    snapshot: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    tree: object = snapshot.memo.get(_NATIVE_TREE_MEMO_KEY)
    if isinstance(tree, _native.NativeProjectTree):
        return tree
    created: _native.NativeProjectTree = _native.NativeProjectTree(str(project_dir))
    snapshot.memo[_NATIVE_TREE_MEMO_KEY] = created
    return created


def seed_snapshot_listings(*, project_dir: Path, tree: _native.NativeProjectTree) -> None:
    """Share the native walk's listings with the pass's Python directory snapshot."""

    listings: list[NativeListing] = tree.listings()
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


def native_path_text_supported(text: str) -> bool:
    """Whether a path's text crosses to the native engine unchanged (no surrogate escapes)."""

    return _is_utf8_text(text)


def _is_utf8_text(text: str) -> bool:
    try:
        _ = text.encode(_PATH_ENCODING)
    except UnicodeEncodeError:
        return False
    return True


def _python_version() -> tuple[int, int]:
    return (sys.version_info[0], sys.version_info[1])
