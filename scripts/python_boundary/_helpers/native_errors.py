"""Find code that calls native functions and swallows their failures."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.python_boundary.constants import (
    MODULE_SCOPE,
    NATIVE_MARKER,
    NATIVE_PACKAGE,
    SUPPRESS_NAME,
)
from scripts.python_boundary.models import NativeErrorHandler


def find_native_error_handlers(
    *, source: Path, paths: tuple[Path, ...]
) -> tuple[NativeErrorHandler, ...]:
    """Each handler or `suppress` around a native call that does not unconditionally raise."""
    handlers: list[NativeErrorHandler] = []
    for path in paths:
        tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        native: frozenset[str] = _native_names(tree)
        if not native:
            continue
        relative: str = path.relative_to(source).as_posix()
        for scope, node in _guarded_blocks(tree):
            for line in _swallowing_lines(node=node, native=native):
                handlers.append(NativeErrorHandler(location=f"{relative}::{scope}", line=line))
    return tuple(handlers)


def _native_names(tree: ast.Module) -> frozenset[str]:
    """Names bound to native code: imports from native modules or of native-named functions."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            native_module: bool = _is_native_module(node.module)
            names.update(
                alias.asname or alias.name
                for alias in node.names
                if native_module or NATIVE_MARKER in alias.name
            )
        elif isinstance(node, ast.Import):
            names.update(
                (alias.asname or alias.name).split(".")[0]
                for alias in node.names
                if _is_native_module(alias.name)
            )
    return frozenset(names)


def _is_native_module(module: str) -> bool:
    parts: list[str] = module.split(".")
    return parts[0] == NATIVE_PACKAGE and any(NATIVE_MARKER in part for part in parts[1:])


def _guarded_blocks(tree: ast.Module) -> list[tuple[str, ast.stmt]]:
    """Every `try` and `with` statement, named by its innermost enclosing function."""
    return _collect(node=tree, scope=MODULE_SCOPE, owner=None)


def _collect(*, node: ast.AST, scope: str, owner: str | None) -> list[tuple[str, ast.stmt]]:
    found: list[tuple[str, ast.stmt]] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.ClassDef):
            found.extend(_collect(node=child, scope=scope, owner=child.name))
        elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            name: str = child.name if owner is None else f"{owner}.{child.name}"
            found.extend(_collect(node=child, scope=name, owner=None))
        else:
            if isinstance(child, ast.Try | ast.TryStar | ast.With | ast.AsyncWith):
                found.append((scope, child))
            found.extend(_collect(node=child, scope=scope, owner=owner))
    return found


def _swallowing_lines(*, node: ast.stmt, native: frozenset[str]) -> list[int]:
    if isinstance(node, ast.Try | ast.TryStar):
        if not _calls_native(body=node.body, native=native):
            return []
        return [handler.lineno for handler in node.handlers if not _always_raises(handler)]
    if isinstance(node, ast.With | ast.AsyncWith) and any(
        _is_suppress(item.context_expr) for item in node.items
    ):
        return [node.lineno] if _calls_native(body=node.body, native=native) else []
    return []


def _always_raises(handler: ast.ExceptHandler) -> bool:
    return any(isinstance(statement, ast.Raise) for statement in handler.body)


def _is_suppress(expression: ast.expr) -> bool:
    if not isinstance(expression, ast.Call):
        return False
    function: ast.expr = expression.func
    if isinstance(function, ast.Attribute):
        return function.attr == SUPPRESS_NAME
    return isinstance(function, ast.Name) and function.id == SUPPRESS_NAME


def _calls_native(*, body: list[ast.stmt], native: frozenset[str]) -> bool:
    for statement in body:
        for node in ast.walk(statement):
            if isinstance(node, ast.Call) and _root_name(node.func) in native:
                return True
    return False


def _root_name(expression: ast.expr) -> str | None:
    while isinstance(expression, ast.Attribute):
        expression = expression.value
    return expression.id if isinstance(expression, ast.Name) else None
