"""Parsing helpers for authored Python function files."""

from __future__ import annotations

import ast
from pathlib import Path

from sqlbuild.compiler.discovery.exceptions import ModelSqlParseError


def parse_python_function(contents: str, *, file_path: Path) -> tuple[dict[str, object], str, str]:
    """Parse one @udf-decorated Python function without importing project code."""

    try:
        module: ast.Module = ast.parse(contents, filename=str(file_path))
    except SyntaxError as error:
        raise ModelSqlParseError(
            f"Python function '{file_path}' could not be parsed: {error}"
        ) from error

    matches: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, ast.Call]] = []
    node: ast.stmt
    for node in module.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        decorator: ast.expr
        for decorator in node.decorator_list:
            call: ast.Call | None = _as_udf_call(decorator)
            if call is not None:
                matches.append((node, call))

    if not matches:
        raise ModelSqlParseError(
            f"Python function '{file_path}' must define exactly one function decorated "
            "with @udf(...)"
        )
    if len(matches) > 1:
        raise ModelSqlParseError(
            f"Python function '{file_path}' must define only one function decorated with @udf(...)"
        )

    function_node, decorator_call = matches[0]
    values: dict[str, object] = {}
    keyword: ast.keyword
    for keyword in decorator_call.keywords:
        if keyword.arg is None:
            raise ModelSqlParseError(
                f"Python function '{file_path}' @udf(...) must not use **kwargs expansion"
            )
        try:
            values[keyword.arg] = ast.literal_eval(keyword.value)
        except (ValueError, TypeError) as error:
            raise ModelSqlParseError(
                f"Python function '{file_path}' @udf(...) value for '{keyword.arg}' must be literal"
            ) from error
    if decorator_call.args:
        raise ModelSqlParseError(
            f"Python function '{file_path}' @udf(...) must use keyword arguments only"
        )

    entry_point: object | None = values.get("entry_point")
    if entry_point is None:
        values["entry_point"] = function_node.name
        entry_point = function_node.name
    if not isinstance(entry_point, str) or not entry_point.strip():
        raise ModelSqlParseError(
            f"Python function '{file_path}' @udf(...) entry_point must be a non-empty string"
        )
    return values, entry_point.strip(), _build_warehouse_python_body(module, udf_node=function_node)


def _as_udf_call(decorator: ast.expr) -> ast.Call | None:
    if not isinstance(decorator, ast.Call):
        return None
    function: ast.expr = decorator.func
    if isinstance(function, ast.Name) and function.id == "udf":
        return decorator
    if isinstance(function, ast.Attribute) and function.attr == "udf":
        return decorator
    return None


def _build_warehouse_python_body(
    module: ast.Module, *, udf_node: ast.FunctionDef | ast.AsyncFunctionDef
) -> str:
    body: list[ast.stmt] = []
    node: ast.stmt
    for node in module.body:
        if _is_sqlbuild_udf_import(node):
            continue
        if node is udf_node:
            clean_function: ast.FunctionDef | ast.AsyncFunctionDef = node
            clean_function.decorator_list = [
                decorator
                for decorator in clean_function.decorator_list
                if _as_udf_call(decorator) is None
            ]
            body.append(clean_function)
            continue
        body.append(node)
    return ast.unparse(ast.Module(body=body, type_ignores=[])).strip()


def _is_sqlbuild_udf_import(node: ast.stmt) -> bool:
    if isinstance(node, ast.ImportFrom):
        return node.module in {"sqlbuild", "sqlbuild.functions"} and any(
            alias.name == "udf" for alias in node.names
        )
    return False
