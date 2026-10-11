"""Identity of the installed SQLBuild code that produces cached compiler and rule results."""

from __future__ import annotations

import json
import platform
from functools import cache
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

import sqlbuild._native as _native

_PACKAGE_NAME: str = "sqlbuild"
_POLYGLOT_PACKAGE_NAME: str = "polyglot-sql-chio"
_YAML_PACKAGE_NAME: str = "PyYAML"
_DIRECT_URL_FILE: str = "direct_url.json"
_PACKAGE_ROOT_PARENT_DEPTH: int = 3


@cache
def installed_code_identity() -> str:
    """Return a digest that changes with every released or locally edited code version."""

    facts: list[str] = [
        _package_version(_PACKAGE_NAME),
        _package_version(_POLYGLOT_PACKAGE_NAME),
        _package_version(_YAML_PACKAGE_NAME),
        platform.python_implementation(),
        ".".join(platform.python_version_tuple()[:2]),
    ]
    package_root: Path | None = (
        Path(__file__).resolve().parents[_PACKAGE_ROOT_PARENT_DEPTH]
        if _is_editable_install()
        else None
    )
    return _native.installed_code_identity(
        facts, None if package_root is None else str(package_root)
    )


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
