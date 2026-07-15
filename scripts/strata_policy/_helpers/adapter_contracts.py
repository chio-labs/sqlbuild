"""Adapter contract ownership analysis for SQLBuild custom rules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from strata import RuleContext

from scripts.strata_policy._helpers.ast_checks import base_name
from scripts.strata_policy.constants import (
    ABSTRACT_METHOD_DECORATOR_NAME,
    ADAPTER_CLASS_MODULE_MIN_PARTS,
    ADAPTER_CONTRACT_CLASSES_PATH,
    ADAPTERS_ROOT_PARTS,
    CLASSES_PACKAGE_NAME,
    CLIENT_MODULE_NAME,
    CLIENT_STYLE_PREFIXES,
    LEGACY_DUCKDB_ADAPTER_SUFFIX,
)


def adapter_contract_class_names(
    *, path_parts: tuple[str, ...], module: ast.Module
) -> frozenset[str]:
    """Return first-class adapter classes owned by the current module."""

    path_text: str = "/".join(path_parts)
    is_builtin_class_module: bool = (
        len(path_parts) >= ADAPTER_CLASS_MODULE_MIN_PARTS
        and path_parts[:3] == ADAPTERS_ROOT_PARTS
        and path_parts[-2] == CLASSES_PACKAGE_NAME
        and path_parts[-1].endswith("_adapter.py")
    )
    is_shared_adapter_class: bool = path_text.endswith(
        "src/sqlbuild/adapter/contract/classes/duckdb_backed_adapter.py"
    )
    is_client_adapter: bool = (
        path_parts[:3] in CLIENT_STYLE_PREFIXES and path_parts[-1] == CLIENT_MODULE_NAME
    )
    is_legacy_duckdb_adapter: bool = path_parts[-3:] == LEGACY_DUCKDB_ADAPTER_SUFFIX
    if not (
        is_builtin_class_module
        or is_shared_adapter_class
        or is_client_adapter
        or is_legacy_duckdb_adapter
    ):
        return frozenset()
    return frozenset(
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef) and node.name.endswith("Adapter")
    )


def abstract_adapter_method_names(*, ctx: RuleContext) -> frozenset[str]:
    """Return abstract adapter method names through tracked project analysis."""

    contract_directory: Path = ctx.repo_root / ADAPTER_CONTRACT_CLASSES_PATH
    contract_paths: tuple[Path, ...] = ctx.project.glob(
        requester=ctx.path,
        path=contract_directory,
        pattern="*.py",
    )
    method_names: set[str] = set()
    contract_path: Path
    for contract_path in contract_paths:
        analysis: Any | None = ctx.project.analysis(requester=ctx.path, path=contract_path)
        if analysis is None:
            continue
        contract_module: ast.Module = ast.parse(analysis.text.source)
        node: ast.AST
        for node in ast.walk(contract_module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(
                base_name(decorator) == ABSTRACT_METHOD_DECORATOR_NAME
                for decorator in node.decorator_list
            ):
                method_names.add(node.name)
    return frozenset(method_names)
