"""The decorator locator the native resource diagnostics call for authored Python functions."""

from __future__ import annotations

import ast


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
