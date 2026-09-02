"""Adapter contract ownership analysis for SQLBuild custom rules."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from fensu import ClassDeclarationFact, RuleContext

from scripts.fensu_policy.constants import (
    ABC_MODULE_NAME,
    ABSTRACT_METHOD_DECORATOR_NAME,
    ADAPTER_BUILTINS_PATH,
    ADAPTER_CLASS_MODULE_MIN_PARTS,
    ADAPTER_CONTRACT_BASE_SYMBOLS,
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
    *, path_parts: tuple[str, ...], ctx: RuleContext
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
    declarations: tuple[ClassDeclarationFact, ...] = tuple(
        declaration for declaration in ctx.facts.class_declarations() if declaration.top_level
    )
    registered_names: frozenset[str] = _builtin_adapter_class_names(ctx=ctx)
    tree: ast.Module = ast.parse(ctx.text.source)
    import_bindings: dict[str, tuple[str, ...]] = _import_bindings(tree=tree)
    class_bases: dict[str, tuple[tuple[str, ...], ...]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        references: list[tuple[str, ...]] = []
        for base in node.bases:
            reference: tuple[str, ...] | None = _reference_parts(expression=base)
            if reference is not None:
                references.append(reference)
        class_bases[node.name] = tuple(references)
    proven_names: set[str] = set()
    changed: bool = True
    while changed:
        changed = False
        for declaration in declarations:
            if declaration.name in proven_names:
                continue
            base_references: tuple[tuple[str, ...], ...] = class_bases.get(declaration.name, ())
            proven_base: bool = any(
                reference in ADAPTER_CONTRACT_BASE_SYMBOLS
                or _resolve_reference(reference=reference, bindings=import_bindings)
                in ADAPTER_CONTRACT_BASE_SYMBOLS
                or (len(reference) == 1 and reference[0] in proven_names)
                for reference in base_references
            )
            if proven_base:
                proven_names.add(declaration.name)
                changed = True
    checked_names: frozenset[str] = frozenset(
        declaration.name
        for declaration in declarations
        if declaration.name.endswith("Adapter")
        and (declaration.name in proven_names or declaration.name in registered_names)
    )
    if is_builtin_class_module:
        checked_names &= registered_names
    elif not (is_shared_adapter_class or is_client_adapter or is_legacy_duckdb_adapter):
        return frozenset()
    return checked_names


def _import_bindings(*, tree: ast.Module) -> dict[str, tuple[str, ...]]:
    bindings: dict[str, tuple[str, ...]] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                source: tuple[str, ...] = tuple(alias.name.split("."))
                bindings[alias.asname or source[0]] = source if alias.asname else (source[0],)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            module_parts: tuple[str, ...] = tuple(node.module.split("."))
            for alias in node.names:
                bindings[alias.asname or alias.name] = module_parts + tuple(alias.name.split("."))
    return bindings


def _reference_parts(*, expression: ast.expr) -> tuple[str, ...] | None:
    if isinstance(expression, ast.Name):
        return (expression.id,)
    if isinstance(expression, ast.Attribute):
        owner: tuple[str, ...] | None = _reference_parts(expression=expression.value)
        return None if owner is None else owner + (expression.attr,)
    return None


def _resolve_reference(
    *, reference: tuple[str, ...], bindings: dict[str, tuple[str, ...]]
) -> tuple[str, ...]:
    bound: tuple[str, ...] | None = bindings.get(reference[0])
    return reference if bound is None else bound + reference[1:]


def abstract_adapter_method_names(*, ctx: RuleContext) -> frozenset[str]:
    """Return abstract adapter method names through tracked project analysis."""

    contract_directory: Path = ctx.repo_root / ADAPTER_CONTRACT_CLASSES_PATH
    contract_paths: tuple[Path, ...] = ctx.project.glob(
        requester=ctx.path,
        path=contract_directory,
        pattern="*.py",
    )
    classes: dict[str, tuple[ClassDeclarationFact, frozenset[str]]] = {}
    contract_path: Path
    for contract_path in contract_paths:
        analysis: Any | None = ctx.project.analysis(requester=ctx.path, path=contract_path)
        if analysis is None:
            continue
        abstract_names: set[str] = {ABSTRACT_METHOD_DECORATOR_NAME}
        for imported in analysis.facts.references().imports:
            if imported.module_parts == (ABC_MODULE_NAME,):
                abstract_names.update(
                    alias.bound_name
                    for alias in imported.aliases
                    if alias.imported_name == ABSTRACT_METHOD_DECORATOR_NAME
                )
        declaration: ClassDeclarationFact
        for declaration in analysis.facts.class_declarations():
            if declaration.top_level:
                classes[declaration.name] = (declaration, frozenset(abstract_names))

    method_names: set[str] = set()
    pending_class_names: list[str] = [STRICT_ADAPTER_CLASS_NAME]
    visited_class_names: set[str] = set()
    while pending_class_names:
        class_name: str = pending_class_names.pop()
        if class_name in visited_class_names or class_name not in classes:
            continue
        visited_class_names.add(class_name)
        declaration: ClassDeclarationFact
        class_abstract_names: frozenset[str]
        declaration, class_abstract_names = classes[class_name]
        pending_class_names.extend(declaration.base_names)
        for method in declaration.methods:
            if {
                decorator_name.rsplit(".", maxsplit=1)[-1]
                for decorator_name in method.decorator_names
            } & class_abstract_names:
                method_names.add(method.name)
    return frozenset(method_names)


def _builtin_adapter_class_names(*, ctx: RuleContext) -> frozenset[str]:
    builtins_path: Path = ctx.repo_root / ADAPTER_BUILTINS_PATH
    analysis: Any | None = ctx.project.analysis(requester=ctx.path, path=builtins_path)
    if analysis is None:
        return frozenset()
    class_names: set[str] = set()
    for imported in analysis.facts.references().imports:
        module_name: str = ".".join(imported.module_parts)
        if not imported.from_import or not module_name.startswith(ADAPTER_PACKAGE_IMPORT_PREFIX):
            continue
        class_names.update(alias.imported_name for alias in imported.aliases)
    return frozenset(class_names)
