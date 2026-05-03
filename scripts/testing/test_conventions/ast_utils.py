"""AST helpers for test convention checks."""

from __future__ import annotations

import ast


def is_docstring_only_module(module: ast.Module) -> bool:
    """Return whether the module is empty or docstring-only."""

    if not module.body:
        return True

    if len(module.body) != 1:
        return False

    statement: ast.stmt = module.body[0]
    if not isinstance(statement, ast.Expr):
        return False
    return isinstance(statement.value, ast.Constant) and isinstance(statement.value.value, str)


def is_dataclass_decorator(decorator: ast.expr) -> bool:
    """Return whether an AST decorator node represents dataclass."""

    if isinstance(decorator, ast.Name):
        return decorator.id == "dataclass"
    if isinstance(decorator, ast.Attribute):
        return decorator.attr == "dataclass"
    if isinstance(decorator, ast.Call):
        return is_dataclass_decorator(decorator.func)
    return False


def is_parametrize_decorator(decorator: ast.expr) -> bool:
    """Return whether an AST decorator node represents pytest.mark.parametrize."""

    if not isinstance(decorator, ast.Call):
        return False

    function: ast.expr = decorator.func
    if not isinstance(function, ast.Attribute) or function.attr != "parametrize":
        return False

    mark: ast.expr = function.value
    return isinstance(mark, ast.Attribute) and mark.attr == "mark"


def attribute_chain(expression: ast.expr) -> tuple[str, ...] | None:
    """Return the dotted name for a Name/Attribute chain."""

    parts: list[str] = []
    current: ast.expr = expression
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value

    if isinstance(current, ast.Name):
        parts.append(current.id)
        return tuple(reversed(parts))

    return None


def extract_name_constant(expression: ast.expr) -> str | None:
    """Return a constant string value when available."""

    if isinstance(expression, ast.Constant) and isinstance(expression.value, str):
        return expression.value
    return None
