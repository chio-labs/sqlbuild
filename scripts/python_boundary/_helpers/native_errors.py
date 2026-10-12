"""Find functions that call the native module and swallow its failures."""

from __future__ import annotations

import ast
from pathlib import Path

from scripts.python_boundary.constants import NATIVE_MODULE, NATIVE_NAME, NATIVE_PACKAGE
from scripts.python_boundary.models import NativeErrorHandler


def find_native_error_handlers(
    *, source: Path, paths: tuple[Path, ...]
) -> tuple[NativeErrorHandler, ...]:
    """Each `try` around a native call whose handler neither raises nor re-raises."""
    handlers: list[NativeErrorHandler] = []
    for path in paths:
        tree: ast.Module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        native: frozenset[str] = _native_names(tree)
        if not native:
            continue
        relative: str = path.relative_to(source).as_posix()
        for function, statement in _try_statements(tree):
            if not _calls_native(body=statement.body, native=native):
                continue
            for handler in statement.handlers:
                if not any(isinstance(node, ast.Raise) for node in ast.walk(handler)):
                    handlers.append(
                        NativeErrorHandler(location=f"{relative}::{function}", line=handler.lineno)
                    )
    return tuple(handlers)


def _native_names(tree: ast.Module) -> frozenset[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module.startswith(NATIVE_MODULE):
                names.update(alias.asname or alias.name for alias in node.names)
            elif node.module == NATIVE_PACKAGE:
                names.update(
                    alias.asname or alias.name for alias in node.names if alias.name == NATIVE_NAME
                )
        elif isinstance(node, ast.Import):
            names.update(
                (alias.asname or alias.name).split(".")[0]
                for alias in node.names
                if alias.name.startswith(NATIVE_MODULE)
            )
    return frozenset(names)


def _try_statements(tree: ast.Module) -> list[tuple[str, ast.Try]]:
    found: list[tuple[str, ast.Try]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            found.extend(
                (node.name, child) for child in ast.walk(node) if isinstance(child, ast.Try)
            )
    return found


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
