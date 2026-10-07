"""The environment stored macro call results are valid in: build, interpreter, code and files."""

from __future__ import annotations

import functools
import importlib.machinery
import json
import os
import sys
import sysconfig
from collections.abc import Iterable
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.macro_bridge.constants import (
    INSTALLED_DISTRIBUTION_SUFFIX,
    INSTALLED_PACKAGE_DIRECTORY_NAMES,
    INSTALLED_RECORD_FILE_NAME,
    INTERPRETER_MODULE_ORIGINS,
    MACRO_CALL_STORE_ENVIRONMENT_VERSION,
    MISSING_SEARCH_PATH_STAMP,
    MODULE_DIGEST_ROW_FIELDS,
    PROJECT_ROOT_SEARCH_PATH_STAMP,
    STORE_TRACKED_ENVIRONMENT_PREFIXES,
    STORE_UNTRACKED_ENVIRONMENT_NAMES,
)
from sqlbuild.compiler.macro_bridge.models import ModuleSources


def project_fingerprint(*, project_dir: Path, model_paths: list[str]) -> str:
    """Digest every project file but model SQL files; OSError if a file is unreadable."""

    return _native.fingerprint_project_files(str(project_dir), model_paths)


def store_environment(*, project_dir: Path, fingerprint: str) -> str:
    """Digest the build, interpreter, import path, installed packages, variables and project."""

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
            json.dumps(_installed_distribution_records()),
            fingerprint,
        ]
    )


def module_sources(modules: Iterable[object]) -> ModuleSources:
    """Files backing `modules` outside the interpreter and SQLBuild, and whether all have one."""

    paths: list[str] = []
    for module in modules:
        path: str | None
        known: bool
        path, known = _backing_file(module)
        if not known:
            return ModuleSources(paths=(), complete=False)
        if path is not None and not _covered_without_content(path):
            paths.append(path)
    return ModuleSources(paths=tuple(paths), complete=True)


def digest_module_files(paths: Iterable[str]) -> dict[str, str] | None:
    """Content digest of each module file, or None when any file cannot be read."""

    ordered: list[str] = list(dict.fromkeys(paths))
    digests: list[str | None] = _native.digest_files(ordered)
    if any(digest is None for digest in digests):
        return None
    return {path: digest for path, digest in zip(ordered, digests, strict=True) if digest}


def module_digests_metadata(digests: dict[str, str]) -> bytes:
    """Encode module file digests for the store's metadata."""

    return json.dumps(sorted([path, digest] for path, digest in digests.items())).encode()


def unchanged_module_digests(*, metadata: bytes, known: dict[str, str]) -> dict[str, str] | None:
    """Return the stored module digests when every module file still has them, else None."""

    try:
        rows: object = json.loads(metadata)
    except ValueError:
        return None
    if not isinstance(rows, list) or not all(map(_is_digest_row, rows)):
        return None
    stored: dict[str, str] = {row[0]: row[1] for row in rows}
    unknown: list[str] = [path for path in stored if path not in known]
    current: dict[str, str] | None = digest_module_files(unknown)
    if current is None:
        return None
    current.update((path, known[path]) for path in stored if path in known)
    return stored if current == stored else None


def _is_digest_row(row: object) -> bool:
    return (
        isinstance(row, list)
        and len(row) == MODULE_DIGEST_ROW_FIELDS
        and all(isinstance(field, str) for field in row)
    )


def _backing_file(module: object) -> tuple[str | None, bool]:
    spec: object = getattr(module, "__spec__", None)
    file: object = getattr(module, "__file__", None)
    if spec is None:
        return (file, True) if isinstance(file, str) and os.path.isfile(file) else (None, True)
    origin: object = getattr(spec, "origin", None)
    if getattr(spec, "has_location", False) and isinstance(origin, str):
        return origin, True
    if origin in INTERPRETER_MODULE_ORIGINS:
        return None, True
    if (
        origin is None
        and file is None
        and getattr(spec, "submodule_search_locations", None) is not None
    ):
        return None, True
    return None, False


def _covered_without_content(path: str) -> bool:
    installed, interpreter, own = _excluded_prefixes()
    if path.startswith(own):
        return True
    if path.startswith(installed):
        return path.endswith(tuple(importlib.machinery.EXTENSION_SUFFIXES))
    return path.startswith(interpreter)


@functools.cache
def _excluded_prefixes() -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    return (
        _directory_prefixes(_installed_directories()),
        _directory_prefixes(sysconfig.get_paths().get(name) for name in ("stdlib", "platstdlib")),
        _directory_prefixes([os.path.dirname(_native.__file__)]),
    )


@functools.cache
def _installed_directories() -> tuple[str, ...]:
    paths: dict[str, str] = sysconfig.get_paths()
    return tuple(
        dict.fromkeys(
            [
                *(paths[name] for name in ("purelib", "platlib") if name in paths),
                *(
                    entry
                    for entry in sys.path
                    if os.path.basename(entry) in INSTALLED_PACKAGE_DIRECTORY_NAMES
                ),
            ]
        )
    )


def _installed_distribution_records() -> list[tuple[str, str | None]]:
    records: list[str] = []
    for directory in _installed_directories():
        records.extend(_distribution_records(directory))
    records.sort()
    return list(zip(records, _native.digest_files(records), strict=True))


def _distribution_records(directory: str) -> list[str]:
    try:
        with os.scandir(directory) as entries:
            return [
                os.path.join(entry.path, INSTALLED_RECORD_FILE_NAME)
                for entry in entries
                if entry.name.endswith(INSTALLED_DISTRIBUTION_SUFFIX)
            ]
    except OSError:
        return []


def _directory_prefixes(directories: Iterable[str | None]) -> tuple[str, ...]:
    prefixes: list[str] = []
    for directory in filter(None, directories):
        prefixes.extend(os.path.join(form, "") for form in (directory, os.path.realpath(directory)))
    return tuple(dict.fromkeys(prefixes))


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
