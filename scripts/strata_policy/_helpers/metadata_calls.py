"""Warehouse metadata call-flow analysis for SQLBuild custom rules."""

from __future__ import annotations

import ast

from scripts.strata_policy.constants import WAREHOUSE_METADATA_METHODS


def metadata_bearing_helper_names(*, module: ast.Module) -> tuple[frozenset[str], frozenset[str]]:
    """Return local method and function names that transitively query metadata."""

    parents: dict[ast.AST, ast.AST] = parent_nodes(module)
    method_calls_by_function: dict[ast.AST, set[str]] = {}
    function_calls_by_function: dict[ast.AST, set[str]] = {}
    directly_bearing: set[ast.AST] = set()
    method_names_by_function: dict[ast.AST, str] = {}
    function_names_by_function: dict[ast.AST, str] = {}

    definition: ast.AST
    for definition in ast.walk(module):
        if not isinstance(definition, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        method_calls: set[str] = set()
        function_calls: set[str] = set()
        called: ast.AST
        for called in ast.walk(definition):
            if not isinstance(called, ast.Call):
                continue
            if isinstance(called.func, ast.Attribute):
                method_calls.add(called.func.attr)
                if called.func.attr in WAREHOUSE_METADATA_METHODS:
                    directly_bearing.add(definition)
            elif isinstance(called.func, ast.Name):
                function_calls.add(called.func.id)
        method_calls_by_function[definition] = method_calls
        function_calls_by_function[definition] = function_calls
        if is_method_definition(definition=definition, parents=parents):
            method_names_by_function[definition] = definition.name
        else:
            function_names_by_function[definition] = definition.name

    bearing: set[ast.AST] = set(directly_bearing)
    changed: bool = True
    while changed:
        changed = False
        bearing_method_names: set[str] = {
            method_names_by_function[function]
            for function in bearing
            if function in method_names_by_function
        }
        bearing_function_names: set[str] = {
            function_names_by_function[function]
            for function in bearing
            if function in function_names_by_function
        }
        function: ast.AST
        for function in method_calls_by_function:
            if function in bearing:
                continue
            if method_calls_by_function[function] & bearing_method_names or (
                function_calls_by_function[function] & bearing_function_names
            ):
                bearing.add(function)
                changed = True

    return (
        frozenset(
            method_names_by_function[function]
            for function in bearing
            if function in method_names_by_function
        ),
        frozenset(
            function_names_by_function[function]
            for function in bearing
            if function in function_names_by_function
        ),
    )


def metadata_call_label(
    *,
    node: ast.Call,
    bearing_method_names: frozenset[str],
    bearing_function_names: frozenset[str],
) -> str | None:
    """Return a diagnostic label when a call reaches warehouse metadata."""

    if isinstance(node.func, ast.Attribute):
        if node.func.attr in WAREHOUSE_METADATA_METHODS:
            return f".{node.func.attr}"
        if node.func.attr in bearing_method_names:
            return node.func.attr
        return None
    if isinstance(node.func, ast.Name) and node.func.id in bearing_function_names:
        return node.func.id
    return None


def parent_nodes(module: ast.Module) -> dict[ast.AST, ast.AST]:
    """Return direct AST parent relationships."""

    parents: dict[ast.AST, ast.AST] = {}
    parent: ast.AST
    for parent in ast.walk(module):
        child: ast.AST
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def is_method_definition(*, definition: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return whether a function is nested beneath a class."""

    current: ast.AST = definition
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.ClassDef):
            return True
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
    return False
