"""Locate tests that replace attributes of the native extension module."""

from __future__ import annotations

import ast

from scripts.fensu_policy.constants import (
    NATIVE_MODULE_NAME,
    NATIVE_MODULE_PACKAGE,
    NATIVE_MODULE_PATH,
    NATIVE_PATCH_CALL_NAMES,
    NATIVE_STRING_PATCH_CALL_NAMES,
)


def _native_names(*, tree: ast.Module) -> frozenset[str]:
    names: set[str] = set()
    node: ast.AST
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(
                alias.asname
                for alias in node.names
                if alias.name == NATIVE_MODULE_PATH and alias.asname
            )
        elif isinstance(node, ast.ImportFrom) and node.module == NATIVE_MODULE_PACKAGE:
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if alias.name == NATIVE_MODULE_NAME
            )
    return frozenset(names)


def _call_name(*, call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def _patches_native(*, call: ast.Call, native_names: frozenset[str]) -> bool:
    if not call.args:
        return False
    target: ast.expr = call.args[0]
    name: str | None = _call_name(call=call)
    if name in NATIVE_PATCH_CALL_NAMES:
        if isinstance(target, ast.Name) and target.id in native_names:
            return True
        if isinstance(target, ast.Attribute) and ast.unparse(target) == NATIVE_MODULE_PATH:
            return True
    return (
        name in NATIVE_STRING_PATCH_CALL_NAMES
        and isinstance(target, ast.Constant)
        and isinstance(target.value, str)
        and target.value.startswith(NATIVE_MODULE_PATH + ".")
    )


def native_patch_lines(*, tree: ast.Module) -> list[int]:
    """Line numbers of calls that replace an attribute of `sqlbuild._native`."""

    native_names: frozenset[str] = _native_names(tree=tree)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _patches_native(call=node, native_names=native_names)
    ]
