"""Identity of the installed code that produces cached compile facts."""

from __future__ import annotations

import hashlib
import json
import platform
from functools import cache
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

import sqlbuild

_PACKAGE_NAME: str = "sqlbuild"
_POLYGLOT_PACKAGE_NAME: str = "polyglot-sql-chio"
_YAML_PACKAGE_NAME: str = "PyYAML"
_DIRECT_URL_FILE: str = "direct_url.json"
_SOURCE_SUFFIXES: frozenset[str] = frozenset({".py", ".so", ".pyd"})


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
        package_root: Path = Path(sqlbuild.__file__).resolve().parent
        for path in sorted(package_root.rglob("*")):
            if path.suffix not in _SOURCE_SUFFIXES or "__pycache__" in path.parts:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            digest.update(
                f"{path.relative_to(package_root)}\0{stat.st_size}\0{stat.st_mtime_ns}\0".encode()
            )
    return str(digest.hexdigest())


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
