"""Shared decoding of the plain-data payloads native discovery returns."""

from __future__ import annotations

import os
import sys
import unicodedata
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.classes.directory_snapshot import DirectorySnapshot
from sqlbuild.compiler.discovery.constants import (
    NATIVE_FAILED_TAG,
    NATIVE_SUPPORTED_PYTHON_VERSIONS,
    NATIVE_UNLISTABLE_TAG,
    NATIVE_UNREADABLE_TAG,
)
from sqlbuild.compiler.discovery.exceptions import (
    DeclarationParseError,
    DiscoveryError,
    ModelSqlParseError,
    ProjectPathError,
    SchemaParseError,
    SourceParseError,
    SqlScenarioParseError,
    SqlTestParseError,
    UnsupportedPythonError,
)
from sqlbuild.compiler.discovery.models import DiscoveryFileFault
from sqlbuild.compiler.discovery.types import (
    DirectorySnapshotEntry,
    NativeListing,
    NativeLocation,
)
from sqlbuild.spec.contracts.models import SourceLocation

_DISPLAY_PROBE: str = "_"
_PATH_ENCODING: str = "utf-8"
_DECODE_ENCODING: str = "utf-8"
_DECODE_READ_KIND: str = "decode"
_NATIVE_TREE_MEMO_KEY: str = "native_project_tree"
_PROJECT_PATH_KIND: str = "project_path"
_SURROGATE_ESCAPE_BASE: int = 0xDC00
_ESCAPED_BYTE_FIRST: int = 0xDC80
_ESCAPED_BYTE_LAST: int = 0xDCFF
_SURROGATE_FIRST: int = 0xD800
_SURROGATE_LAST: int = 0xDFFF
_FAILURE_CLASSES: dict[str, type[DiscoveryError]] = {
    "model_sql": ModelSqlParseError,
    "declaration": DeclarationParseError,
    "sql_test": SqlTestParseError,
    "sql_scenario": SqlScenarioParseError,
    "schema": SchemaParseError,
    "source": SourceParseError,
    _PROJECT_PATH_KIND: ProjectPathError,
}


def native_display_prefix(project_dir: Path) -> str:
    """Return the text `str(project_dir / name)` prints before `name`."""

    return str(project_dir / _DISPLAY_PROBE)[: -len(_DISPLAY_PROBE)]


def native_failure(payload: tuple[object, ...]) -> DiscoveryError:
    """Build the discovery error a native failure payload describes."""

    _tag, kind, message, help_text = payload
    error_class: type[DiscoveryError] = _FAILURE_CLASSES[str(kind)]
    return error_class(str(message), help=None if help_text is None else str(help_text))


def native_read_error(*, payload: tuple[object, ...], file_path: Path) -> Exception:
    """Build the error Python's `read_text` raises for a file native discovery could not read."""

    if payload[1] == _DECODE_READ_KIND:
        _tag, _kind, data, start, end, reason = payload
        return UnicodeDecodeError(
            _DECODE_ENCODING, cast(bytes, data), cast(int, start), cast(int, end), str(reason)
        )
    _tag, _kind, errno, message, winerror = payload
    if winerror is not None:
        return OSError(None, str(message), str(file_path), cast(int, winerror))
    if errno is None:
        return OSError(str(message))
    return OSError(errno, os.strerror(cast(int, errno)), str(file_path))


def native_payload_error(*, payload: tuple[object, ...], file_path: Path) -> Exception | None:
    """Return the error a failed or unreadable file payload raises, or `None` for a parsed one."""

    tag: object = payload[0]
    if tag == NATIVE_FAILED_TAG:
        return native_failure(payload)
    if tag == NATIVE_UNREADABLE_TAG:
        return native_read_error(payload=payload, file_path=file_path)
    return None


def native_collection[ResultT](
    *, result: ResultT | tuple[object, ...], project_dir: Path
) -> ResultT:
    """Return a native collection, raising the error of a collection that could not be read."""

    if not isinstance(result, tuple) or not isinstance(result[0], str):
        return cast(ResultT, result)
    payload: tuple[object, ...] = result
    if payload[0] == NATIVE_UNLISTABLE_TAG:
        _tag, relative_path, read_payload = payload
        raise native_read_error(
            payload=cast(tuple[object, ...], read_payload),
            file_path=project_dir / str(relative_path),
        )
    raise native_failure(payload)


def load_native_yaml_document(*, contents: str, file_path: Path, kind: str) -> object:
    """Load one in-memory YAML document as native discovery loads a `kind` file."""

    payload: tuple[object, ...] = _native.load_yaml_document(str(file_path), contents, kind)
    error: Exception | None = native_payload_error(payload=payload, file_path=file_path)
    if error is not None:
        raise error
    return payload[2]


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

    python_version: tuple[int, int] = (sys.version_info[0], sys.version_info[1])
    if not _native.native_text_supported(python_version, unicodedata.unidata_version):
        raise UnsupportedPythonError(
            f"This SQLBuild release supports Python {NATIVE_SUPPORTED_PYTHON_VERSIONS}, not "
            f"Python {python_version[0]}.{python_version[1]} (Unicode "
            f"{unicodedata.unidata_version}); run sqb with a supported Python"
        )
    return {"python_version": python_version, "unicode_version": unicodedata.unidata_version}


def native_project_tree(project_dir: Path) -> _native.NativeProjectTree:
    """Return the native listings shared by every native call of this discovery pass."""

    snapshot: DirectorySnapshot = DirectorySnapshot.current(project_dir=project_dir)
    tree: object = snapshot.memo.get(_NATIVE_TREE_MEMO_KEY)
    if isinstance(tree, _native.NativeProjectTree):
        return tree
    for text in (str(project_dir), native_display_prefix(project_dir)):
        if not native_path_text_supported(text):
            raise ProjectPathError(
                f"Project directory {_escaped(text)} is not valid UTF-8; move the project to a "
                "directory whose path is valid UTF-8"
            )
    created: _native.NativeProjectTree = _native.NativeProjectTree(str(project_dir))
    snapshot.memo[_NATIVE_TREE_MEMO_KEY] = created
    return created


def native_request(*, project_dir: Path, fields: dict[str, object]) -> dict[str, object]:
    """Return a native discovery request for the project with the running Python's semantics."""

    return {
        "project_dir": str(project_dir),
        "display_prefix": native_display_prefix(project_dir),
        **fields,
        **native_text_runtime(),
    }


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

    try:
        _ = text.encode(_PATH_ENCODING)
    except UnicodeEncodeError:
        return False
    return True


def native_unreadable_path_payload(*, project_dir: Path, relative_text: str) -> tuple[object, ...]:
    """Return the per-file failure payload for a path native discovery cannot name, if any."""

    if native_path_text_supported(relative_text):
        return ()
    return (
        NATIVE_FAILED_TAG,
        _PROJECT_PATH_KIND,
        f"Project path {_escaped(str(project_dir / relative_text))} is not valid UTF-8; rename it "
        "so SQLBuild can read it",
        None,
    )


def _escaped(text: str) -> str:
    return "".join(_escaped_character(character) for character in text)


def _escaped_character(character: str) -> str:
    code_point: int = ord(character)
    if _ESCAPED_BYTE_FIRST <= code_point <= _ESCAPED_BYTE_LAST:
        return f"\\x{code_point - _SURROGATE_ESCAPE_BASE:02x}"
    if _SURROGATE_FIRST <= code_point <= _SURROGATE_LAST:
        return f"\\u{code_point:04x}"
    return character
