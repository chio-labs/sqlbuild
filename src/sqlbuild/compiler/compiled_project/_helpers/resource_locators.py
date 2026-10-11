"""Locators the native resource diagnostics call: YAML entries, MODEL header entries, decorators."""

from __future__ import annotations

import ast

from sqlbuild.compiler.discovery.main._model_header_entry_span import get_model_header_entry_span
from sqlbuild.compiler.discovery.main._yaml_entry_line import (
    yaml_entry_line as _yaml_entry_line,
)


def yaml_entry_line(*, contents: str, name: str) -> int | None:
    """The 1-based line of the outermost `- name: <name>` entry, if present."""

    return _yaml_entry_line(contents=contents, name=name)


def model_header_entry_span(*, contents: str, key: str) -> tuple[int, int] | None:
    """The authored offsets of one top-level MODEL header entry."""

    return get_model_header_entry_span(contents=contents, key=key)


def decorator_location(*, contents: str, decorator: str) -> tuple[int, int]:
    """The `@decorator` line and column offset, ignoring docstrings and comments."""

    try:
        module: ast.Module = ast.parse(contents)
    except SyntaxError:
        return 1, 1
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for expression in node.decorator_list:
                if _decorator_name(expression) == decorator:
                    return expression.lineno, expression.col_offset
    return 1, 1


def _decorator_name(expression: ast.expr) -> str | None:
    target: ast.expr = expression.func if isinstance(expression, ast.Call) else expression
    if isinstance(target, ast.Name):
        return target.id
    if isinstance(target, ast.Attribute):
        return target.attr
    return None
