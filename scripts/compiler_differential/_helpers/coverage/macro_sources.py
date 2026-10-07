"""Read one macro function out of the captured source of the file that defines it."""

from __future__ import annotations

import ast

from scripts.compiler_differential.constants import TYPED_REFERENCE_ANNOTATION


def macro_function_source(*, file_source: str, name: str) -> str:
    """Return the source of the top-level function `name`, or "" when the file has none."""

    function: ast.FunctionDef | None = _function(file_source=file_source, name=name)
    if function is None:
        return ""
    return ast.get_source_segment(file_source, function) or ""


def takes_typed_reference(*, file_source: str, name: str) -> bool:
    """Whether the function `name` annotates a parameter with the typed reference type."""

    function: ast.FunctionDef | None = _function(file_source=file_source, name=name)
    if function is None:
        return False
    arguments: ast.arguments = function.args
    return any(
        argument.annotation is not None
        and TYPED_REFERENCE_ANNOTATION in ast.unparse(argument.annotation)
        for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    )


def _function(*, file_source: str, name: str) -> ast.FunctionDef | None:
    try:
        module: ast.Module = ast.parse(file_source)
    except SyntaxError:
        return None
    return next(
        (node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name),
        None,
    )
