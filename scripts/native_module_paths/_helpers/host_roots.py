"""Fensu dead-code roots that keep the native host table's Python targets alive."""

import ast
import importlib.util
import tomllib
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any

import sqlbuild._native_host as native_host
from scripts.native_module_paths.constants import (
    HOST_ROOT_REASON,
    MODULE_FILE_ATTRIBUTE,
    PYTHON_SUFFIX,
)


def defining_target(*, target: tuple[str, str]) -> tuple[str, str]:
    """Follow `from module import name as name` re-exports to the module that defines a target."""
    module, attribute = target
    spec: ModuleSpec | None = importlib.util.find_spec(module)
    origin: str | None = None if spec is None else spec.origin
    if origin is None or not origin.endswith(PYTHON_SUFFIX):
        return target
    for node in ast.parse(Path(origin).read_text(encoding="utf-8")).body:
        if not isinstance(node, ast.ImportFrom) or node.level != 0 or node.module is None:
            continue
        for alias in node.names:
            if (alias.asname or alias.name) == attribute:
                return defining_target(target=(node.module, alias.name))
    return target


def host_targets() -> set[tuple[str, str]]:
    """The defining module and symbol of every host table entry that names a symbol."""
    targets: set[tuple[str, str]] = set()
    for target in native_host.host_targets().values():
        if target[1] != MODULE_FILE_ATTRIBUTE:
            targets.add(defining_target(target=target))
    return targets


def host_dead_code_roots(*, config: Path) -> set[tuple[str, str]]:
    """Every module and symbol the Fensu dead-code roots in `config` keep for the host table."""
    parsed: dict[str, Any] = tomllib.loads(config.read_text(encoding="utf-8"))
    roots: list[dict[str, Any]] = parsed["targets"]["python"]["dead_code"]["roots"]
    found: set[tuple[str, str]] = set()
    for root in roots:
        if root["reason"] != HOST_ROOT_REASON:
            continue
        for module in root["modules"]:
            for symbol in root["symbols"]:
                found.add((module, symbol))
    return found
