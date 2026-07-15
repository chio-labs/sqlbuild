"""AST operations shared by SQLBuild custom Strata rules."""

from __future__ import annotations

import ast

from scripts.strata_policy.constants import (
    DISCARDED_CALL_ALLOWED_NAMES,
    DISCARDED_CALL_ALLOWED_PREFIXES,
    PARAMETER_MUTATION_METHODS,
    PARAMETER_RECEIVER_NAMES,
)


def base_name(node: ast.AST) -> str | None:
    """Return the leftmost or direct name represented by an expression."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return base_name(node.value)
    if isinstance(node, ast.Subscript):
        return base_name(node.value)
    return None


def call_base_name(node: ast.Call) -> str | None:
    """Return the base name of a call target."""

    return base_name(node.func)


def discarded_call_is_allowed(node: ast.Call) -> bool:
    """Return whether a bare discarded call has an approved side-effect name."""

    if not isinstance(node.func, ast.Name):
        return True
    name: str = node.func.id.lstrip("_")
    return name in DISCARDED_CALL_ALLOWED_NAMES or name.startswith(DISCARDED_CALL_ALLOWED_PREFIXES)


def function_parameter_names(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> frozenset[str]:
    """Return mutable input parameter names, excluding method receivers."""

    return frozenset(
        argument.arg
        for argument in (
            *function_node.args.posonlyargs,
            *function_node.args.args,
            *function_node.args.kwonlyargs,
        )
        if argument.arg not in PARAMETER_RECEIVER_NAMES
    )


def parameter_mutated_by_node(*, node: ast.AST, parameter_names: frozenset[str]) -> str | None:
    """Return the parameter mutated directly by an AST node, if any."""

    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        targets: tuple[ast.expr, ...] = (
            tuple(node.targets) if isinstance(node, ast.Assign) else (node.target,)
        )
        for target in targets:
            parameter_name: str | None = root_parameter_name(
                node=target,
                parameter_names=parameter_names,
            )
            if parameter_name is not None and not isinstance(target, ast.Name):
                return parameter_name
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in PARAMETER_MUTATION_METHODS
    ):
        return root_parameter_name(node=node.func.value, parameter_names=parameter_names)
    return None


def root_parameter_name(*, node: ast.AST, parameter_names: frozenset[str]) -> str | None:
    """Return the parameter at the root of an attribute or subscript chain."""

    if isinstance(node, ast.Name):
        return node.id if node.id in parameter_names else None
    if isinstance(node, ast.Attribute):
        return root_parameter_name(node=node.value, parameter_names=parameter_names)
    if isinstance(node, ast.Subscript):
        return root_parameter_name(node=node.value, parameter_names=parameter_names)
    return None


def top_level_class_nodes(module: ast.Module) -> tuple[ast.ClassDef, ...]:
    """Return top-level class declarations in source order."""

    return tuple(node for node in module.body if isinstance(node, ast.ClassDef))
