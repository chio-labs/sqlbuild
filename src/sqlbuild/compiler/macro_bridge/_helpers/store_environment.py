"""The environment stored macro call results are valid in: build, interpreter and project files."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.macro_bridge.constants import (
    MACRO_CALL_STORE_ENVIRONMENT_VERSION,
    MISSING_SEARCH_PATH_STAMP,
    MODULE_STAMP_ROW_FIELDS,
    PROJECT_ROOT_SEARCH_PATH_STAMP,
    STORE_TRACKED_ENVIRONMENT_PREFIXES,
    STORE_UNTRACKED_ENVIRONMENT_NAMES,
)
from sqlbuild.compiler.macro_bridge.types import ModuleStamp


def store_environment(*, project_dir: Path, model_paths: list[str]) -> str:
    """Digest every input but model SQL files and context; OSError if a file is unreadable."""

    fingerprint: str = _native.fingerprint_project_files(str(project_dir), model_paths)
    return _native.content_digest(
        [
            MACRO_CALL_STORE_ENVIRONMENT_VERSION,
            _native.BUILD_IDENTITY,
            sys.version,
            sys.executable,
            sys.platform,
            str(sys.implementation.cache_tag),
            json.dumps(_search_path_stamps(project_dir=project_dir)),
            json.dumps(_tracked_environment()),
            fingerprint,
        ]
    )


def loaded_module_stamps() -> dict[str, ModuleStamp]:
    """Stat every loaded module file, including modules macros imported while running."""

    stamps: dict[str, ModuleStamp] = {}
    for module in tuple(sys.modules.values()):
        path: object = getattr(module, "__file__", None)
        if not isinstance(path, str) or path in stamps:
            continue
        try:
            status: os.stat_result = os.stat(path)
        except OSError:
            continue
        stamps[path] = (status.st_mtime_ns, status.st_size)
    return stamps


def module_stamps_metadata(stamps: dict[str, ModuleStamp]) -> bytes:
    """Encode module stamps for the store's metadata."""

    return json.dumps(sorted([path, *stamp] for path, stamp in stamps.items())).encode()


def unchanged_module_stamps(metadata: bytes) -> dict[str, ModuleStamp] | None:
    """Return the stored module stamps when every module file is unchanged, else None."""

    try:
        rows: object = json.loads(metadata)
    except ValueError:
        return None
    if not isinstance(rows, list):
        return None
    stamps: dict[str, ModuleStamp] = {}
    for row in rows:
        if not (
            isinstance(row, list)
            and len(row) == MODULE_STAMP_ROW_FIELDS
            and isinstance(row[0], str)
            and isinstance(row[1], int)
            and isinstance(row[2], int)
        ):
            return None
        try:
            status: os.stat_result = os.stat(row[0])
        except OSError:
            return None
        if (status.st_mtime_ns, status.st_size) != (row[1], row[2]):
            return None
        stamps[row[0]] = (row[1], row[2])
    return stamps


def _search_path_stamps(*, project_dir: Path) -> list[tuple[str, int]]:
    project_root: str = os.path.realpath(project_dir)
    stamps: list[tuple[str, int]] = []
    for entry in sys.path:
        path: str = entry or "."
        try:
            mtime_ns: int = (
                PROJECT_ROOT_SEARCH_PATH_STAMP
                if os.path.realpath(path) == project_root
                else os.stat(path).st_mtime_ns
            )
        except OSError:
            mtime_ns = MISSING_SEARCH_PATH_STAMP
        stamps.append((entry, mtime_ns))
    return stamps


def _tracked_environment() -> list[tuple[str, str]]:
    return sorted(
        (name, value)
        for name, value in os.environ.items()
        if name.startswith(STORE_TRACKED_ENVIRONMENT_PREFIXES)
        and name not in STORE_UNTRACKED_ENVIRONMENT_NAMES
    )
