"""Identity of the installed code that produces cached compile facts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
from functools import cache
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

_PACKAGE_NAME: str = "sqlbuild"
_POLYGLOT_PACKAGE_NAME: str = "polyglot-sql-chio"
_YAML_PACKAGE_NAME: str = "PyYAML"
_DIRECT_URL_FILE: str = "direct_url.json"
_SOURCE_SUFFIXES: frozenset[str] = frozenset({".py", ".so", ".pyd"})
_BYTECODE_CACHE_DIRECTORY: str = "__pycache__"
_PACKAGE_ROOT_PARENT_DEPTH: int = 3


@cache
def installed_code_identity() -> str:
    """Return a digest that changes with every released or locally edited code version."""

    digest: Any = hashlib.sha256()
    for item in (
        _package_version(_PACKAGE_NAME),
        _package_version(_POLYGLOT_PACKAGE_NAME),
        _package_version(_YAML_PACKAGE_NAME),
        platform.python_implementation(),
        ".".join(platform.python_version_tuple()[:2]),
    ):
        digest.update(item.encode())
        digest.update(b"\0")
    if _is_editable_install():
        package_root: Path = Path(__file__).resolve().parents[_PACKAGE_ROOT_PARENT_DEPTH]
        for relative_path, size, mtime_ns in _source_file_stats(root=package_root):
            digest.update(f"{relative_path}\0{size}\0{mtime_ns}\0".encode())
    return str(digest.hexdigest())


def _source_file_stats(*, root: Path) -> list[tuple[str, int, int]]:
    root_prefix_length: int = len(str(root)) + 1
    stats: list[tuple[str, int, int]] = []
    pending: list[str] = [str(root)]
    while pending:
        directory: str = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name != _BYTECODE_CACHE_DIRECTORY:
                            pending.append(entry.path)
                    elif os.path.splitext(entry.name)[1] in _SOURCE_SUFFIXES:
                        stat: os.stat_result = entry.stat()
                        stats.append(
                            (entry.path[root_prefix_length:], stat.st_size, stat.st_mtime_ns)
                        )
        except OSError:
            continue
    stats.sort()
    return stats


def _package_version(package: str) -> str:
    try:
        return distribution(package).version
    except PackageNotFoundError:
        return "unknown"


def _is_editable_install() -> bool:
    try:
        direct_url: str | None = distribution(_PACKAGE_NAME).read_text(_DIRECT_URL_FILE)
    except PackageNotFoundError:
        return True
    if direct_url is None:
        return False
    try:
        payload: object = json.loads(direct_url)
    except ValueError:
        return True
    if not isinstance(payload, dict):
        return True
    dir_info: object = payload.get("dir_info")
    return isinstance(dir_info, dict) and dir_info.get("editable") is True
