"""Adapter contract ownership analysis for SQLBuild custom rules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from strata import RuleContext

from scripts.strata_policy._helpers.ast_checks import base_name
from scripts.strata_policy.constants import (
    ABC_MODULE_NAME,
    ABSTRACT_METHOD_DECORATOR_NAME,
    ADAPTER_BUILTINS_PATH,
    ADAPTER_CLASS_MODULE_MIN_PARTS,
    ADAPTER_CONTRACT_CLASSES_PATH,
    ADAPTER_PACKAGE_IMPORT_PREFIX,
    ADAPTERS_ROOT_PARTS,
    CLASSES_PACKAGE_NAME,
    CLIENT_MODULE_NAME,
    CLIENT_STYLE_PREFIXES,
    DUCKDB_BACKED_ADAPTER_PATH,
    LEGACY_DUCKDB_ADAPTER_SUFFIX,
    STRICT_ADAPTER_CLASS_NAME,
)


def adapter_contract_class_names(
    *, path_parts: tuple[str, ...], module: ast.Module, ctx: RuleContext
) -> frozenset[str]:
    """Return first-class adapter classes owned by the current module."""

    path_text: str = "/".join(path_parts)
    is_builtin_class_module: bool = (
        len(path_parts) >= ADAPTER_CLASS_MODULE_MIN_PARTS
        and path_parts[:3] == ADAPTERS_ROOT_PARTS
        and path_parts[-2] == CLASSES_PACKAGE_NAME
    )
    is_shared_adapter_class: bool = path_text == DUCKDB_BACKED_ADAPTER_PATH
    is_client_adapter: bool = (
        path_parts[:3] in CLIENT_STYLE_PREFIXES and path_parts[-1] == CLIENT_MODULE_NAME
    )
    is_legacy_duckdb_adapter: bool = path_parts[-3:] == LEGACY_DUCKDB_ADAPTER_SUFFIX
    checked_names: frozenset[str] = frozenset(
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Adapter")
    )
    if is_builtin_class_module:
        checked_names &= _builtin_adapter_class_names(ctx=ctx)
    elif not (is_shared_adapter_class or is_client_adapter or is_legacy_duckdb_adapter):
        return frozenset()
    return checked_names


def abstract_adapter_method_names(*, ctx: RuleContext) -> frozenset[str]:
    """Return abstract adapter method names through tracked project analysis."""

    contract_directory: Path = ctx.repo_root / ADAPTER_CONTRACT_CLASSES_PATH
    contract_paths: tuple[Path, ...] = ctx.project.glob(
        requester=ctx.path,
        path=contract_directory,
        pattern="*.py",
    )
    classes: dict[str, tuple[ast.ClassDef, frozenset[str]]] = {}
    contract_path: Path
    for contract_path in contract_paths:
        analysis: Any | None = ctx.project.analysis(requester=ctx.path, path=contract_path)
        if analysis is None:
            continue
        contract_module: ast.Module = ast.parse(analysis.text.source)
        abstract_names: set[str] = {ABSTRACT_METHOD_DECORATOR_NAME}
        statement: ast.stmt
        for statement in contract_module.body:
            if isinstance(statement, ast.ImportFrom) and statement.module == ABC_MODULE_NAME:
                abstract_names.update(
                    alias.asname or alias.name
                    for alias in statement.names
                    if alias.name == ABSTRACT_METHOD_DECORATOR_NAME
                )
            if isinstance(statement, ast.ClassDef):
                classes[statement.name] = (statement, frozenset(abstract_names))

    method_names: set[str] = set()
    pending_class_names: list[str] = [STRICT_ADAPTER_CLASS_NAME]
    visited_class_names: set[str] = set()
    while pending_class_names:
        class_name: str = pending_class_names.pop()
        if class_name in visited_class_names or class_name not in classes:
            continue
        visited_class_names.add(class_name)
        class_node: ast.ClassDef
        class_abstract_names: frozenset[str]
        class_node, class_abstract_names = classes[class_name]
        pending_class_names.extend(
            resolved_name
            for base in class_node.bases
            if (resolved_name := base_name(base)) is not None
        )
        child: ast.stmt
        for child in class_node.body:
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(
                base_name(decorator) in class_abstract_names for decorator in child.decorator_list
            ):
                method_names.add(child.name)
    return frozenset(method_names)


def _builtin_adapter_class_names(*, ctx: RuleContext) -> frozenset[str]:
    builtins_path: Path = ctx.repo_root / ADAPTER_BUILTINS_PATH
    analysis: Any | None = ctx.project.analysis(requester=ctx.path, path=builtins_path)
    if analysis is None:
        return frozenset()
    builtins_module: ast.Module = ast.parse(analysis.text.source)
    class_names: set[str] = set()
    node: ast.AST
    for node in ast.walk(builtins_module):
        if not isinstance(node, ast.ImportFrom) or not (node.module or "").startswith(
            ADAPTER_PACKAGE_IMPORT_PREFIX
        ):
            continue
        class_names.update(alias.name for alias in node.names)
    return frozenset(class_names)
