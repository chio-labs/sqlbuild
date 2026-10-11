"""Compile-time expansion helpers for authored project SQL macros."""

from __future__ import annotations

import ast
import hashlib
import heapq
import inspect
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import cache, partial
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import cast

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.explicit_references.macro_arguments import (
    call_site_sql_references,
    typed_reference_kinds,
)
from sqlbuild.compiler.compile.constants import (
    DECLARATION_REFERENCE_NAMES,
    MACRO_TOKEN,
)
from sqlbuild.compiler.compile.exceptions import (
    CompileInputError,
    MacroArgumentError,
    MacroDeclarationLookupError,
)
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    DeclarationResolutionContext,
    DeclarationScopeResolver,
    ExpansionSpan,
    LoadedMacro,
    MacroContext,
    MacroExpansionResult,
    StaticMacroExport,
    StaticMacroFault,
    StaticMacroInventory,
)
from sqlbuild.compiler.discovery.main.explicit_references_help import explicit_references_help
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredMacroFile,
    EnumDeclaration,
)
from sqlbuild.compiler.macro_bridge.constants import (
    GENERATED_REFERENCE_MARKERS,
)
from sqlbuild.compiler.macro_bridge.main._macro_store_tokens import macro_store_tokens
from sqlbuild.compiler.macro_bridge.main.active_macro_bridge import active_macro_bridge
from sqlbuild.compiler.resource_names.main._validate_resource_identity import (
    validate_resource_identity,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, ScopeKind, UsageKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.python_nodes.models import RELATION_RENDERER, SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceLocation
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind

_STAR_IMPORT_NAME: str = "*"
_SYNTHETIC_PACKAGE_PREFIX: str = "_sqlbuild_project_macros_"
_OBJECT_ENTRY_LENGTH: int = 2
_MACRO_MODULE_LOAD_LOCK: threading.RLock = threading.RLock()


@dataclass(frozen=True)
class _MacroModuleAnalysis:
    file: DiscoveredMacroFile
    name: str
    tree: ast.Module
    exports: tuple[str, ...]
    dependencies: dict[str, tuple[DeclarationIdentity, ...]]
    module_dependencies: tuple[str, ...]


@dataclass(frozen=True)
class _MacroAnalysisInputs:
    files: dict[str, DiscoveredMacroFile]
    trees: dict[str, ast.Module]
    exports: dict[str, frozenset[str]]
    module_names: frozenset[str]
    package_names: frozenset[str]


class _MacroDeclarationValues(Mapping[str, object]):
    def __init__(
        self,
        *,
        values: Mapping[str, object],
        inaccessible: Mapping[str, DeclarationRecord],
        declaration_kind: str,
        file_path: Path,
        on_access: Callable[[str], None],
        on_miss: Callable[[], None],
    ) -> None:
        self._values: Mapping[str, object] = values
        self._inaccessible: Mapping[str, DeclarationRecord] = inaccessible
        self._declaration_kind: str = declaration_kind
        self._file_path: Path = file_path
        self._on_access: Callable[[str], None] = on_access
        self._on_miss: Callable[[], None] = on_miss

    def __getitem__(self, name: str) -> object:
        if name in self._values:
            self._on_access(name)
            return self._values[name]
        self._on_miss()
        inaccessible: DeclarationRecord | None = self._inaccessible.get(name)
        if inaccessible is not None:
            owner: str = inaccessible.owning_path or "global"
            raise MacroDeclarationLookupError(
                f"{self._declaration_kind.title()} '{name}' in '{self._file_path}' is "
                f"inaccessible. Defined at '{inaccessible.path}:{inaccessible.line}:"
                f"{inaccessible.column}' with scope owner '{owner}'"
            )
        visible: str = ", ".join(sorted(self._values)) or "none"
        raise MacroDeclarationLookupError(
            f"Unknown {self._declaration_kind} '{name}' in '{self._file_path}'. "
            f"Visible {self._declaration_kind}s: {visible}"
        )

    def __iter__(self) -> Iterator[str]:
        for name in self._values:
            self._on_access(name)
            yield name

    def __len__(self) -> int:
        for name in self._values:
            self._on_access(name)
        return len(self._values)


class _MacroEnumMembers(Mapping[str, str | int]):
    def __init__(
        self,
        *,
        enum_name: str,
        values: Mapping[str, str | int],
        file_path: Path,
        on_miss: Callable[[], None],
    ) -> None:
        self._enum_name: str = enum_name
        self._values: Mapping[str, str | int] = values
        self._file_path: Path = file_path
        self._on_miss: Callable[[], None] = on_miss

    def __getitem__(self, name: str) -> str | int:
        if name in self._values:
            return self._values[name]
        self._on_miss()
        available: str = ", ".join(sorted(self._values)) or "none"
        raise MacroDeclarationLookupError(
            f"Unknown member '{name}' for enum '{self._enum_name}' in '{self._file_path}'. "
            f"Available members: {available}"
        )

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def load_project_macros(macro_files: tuple[DiscoveredMacroFile, ...]) -> dict[str, LoadedMacro]:
    """Load discovered project macro functions into a collision-checked registry."""

    if not macro_files:
        return {}
    try:
        analyses: dict[str, _MacroModuleAnalysis] = _analyze_project_macro_modules(
            macro_files=macro_files
        )
    except CompileInputError:
        fault_inventory: StaticMacroInventory = _inventory_project_macros_tolerantly(
            macro_files=macro_files
        )
        raise CompileInputError(fault_inventory.faults[0].message) from None
    inventory: StaticMacroInventory = _inventory_from_analyses(
        macro_files=macro_files, analyses=analyses
    )
    if inventory.faults:
        raise CompileInputError(inventory.faults[0].message)

    modules: dict[str, ModuleType] = _load_macro_modules(analyses=analyses)
    export_dependencies: dict[tuple[Path, str], tuple[DeclarationIdentity, ...]] = {
        (item.relative_path, item.name): item.dependencies for item in inventory.exports
    }
    loaded_macros: dict[str, LoadedMacro] = {}
    for macro_file in macro_files:
        module: ModuleType = modules[_macro_module_name(macro_file)]
        attribute_name: str
        for attribute_name in dir(module):
            if attribute_name.startswith("_"):
                continue
            attribute_value: object = getattr(module, attribute_name)
            if (
                not inspect.isfunction(attribute_value)
                or attribute_value.__module__ != module.__name__
            ):
                continue
            validate_resource_identity(
                name=attribute_name,
                kind="macro",
                path=macro_file.relative_path,
            )
            existing_macro: LoadedMacro | None = loaded_macros.get(attribute_name)
            if existing_macro is not None:
                raise CompileInputError(
                    f"Macro name collision for '{attribute_name}': "
                    f"{existing_macro.file_path} and {macro_file.file_path}"
                )
            loaded_macros[attribute_name] = LoadedMacro(
                name=attribute_name,
                file_path=macro_file.file_path,
                relative_path=macro_file.relative_path,
                raw_source=macro_file.contents,
                function=attribute_value,
                dependencies=export_dependencies[(macro_file.relative_path, attribute_name)],
            )
    return loaded_macros


def _macro_inventory_fault(
    *, error: CompileInputError, macro_files: tuple[DiscoveredMacroFile, ...]
) -> StaticMacroFault:
    relative_path: Path = next(
        (item.relative_path for item in macro_files if item.relative_path.as_posix() in str(error)),
        macro_files[0].relative_path if macro_files else Path("macros"),
    )
    return StaticMacroFault(relative_path=relative_path, message=str(error))


def _inventory_project_macros_tolerantly(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> StaticMacroInventory:
    remaining: list[DiscoveredMacroFile] = list(macro_files)
    faults: list[StaticMacroFault] = []
    while remaining:
        current: tuple[DiscoveredMacroFile, ...] = tuple(remaining)
        try:
            analyses: dict[str, _MacroModuleAnalysis] = _analyze_project_macro_modules(
                macro_files=current
            )
        except CompileInputError as error:
            collisions: tuple[tuple[str, tuple[DiscoveredMacroFile, ...]], ...] = (
                _macro_module_path_collisions(macro_files=current)
            )
            if collisions:
                collided_paths: set[Path] = set()
                for module_name, files in collisions:
                    paths: str = " and ".join(str(file.relative_path) for file in files)
                    for file in files:
                        collided_paths.add(file.relative_path)
                        faults.append(
                            StaticMacroFault(
                                relative_path=file.relative_path,
                                message=(
                                    f"Macro module path collision for '{module_name}': {paths}"
                                ),
                            )
                        )
                remaining = [item for item in remaining if item.relative_path not in collided_paths]
                continue
            fault: StaticMacroFault = _macro_inventory_fault(error=error, macro_files=current)
            faults.append(fault)
            remaining = [item for item in remaining if item.relative_path != fault.relative_path]
            continue
        inventory: StaticMacroInventory = _inventory_from_analyses(
            macro_files=current, analyses=analyses
        )
        return StaticMacroInventory(
            exports=inventory.exports,
            faults=_deduplicated_macro_faults((*faults, *inventory.faults)),
        )
    return StaticMacroInventory(faults=_deduplicated_macro_faults(tuple(faults)))


def _macro_module_path_collisions(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> tuple[tuple[str, tuple[DiscoveredMacroFile, ...]], ...]:
    grouped: dict[str, list[DiscoveredMacroFile]] = {}
    for file in macro_files:
        grouped.setdefault(_macro_module_name(file), []).append(file)
    collisions: list[tuple[str, tuple[DiscoveredMacroFile, ...]]] = []
    for module_name in sorted(grouped):
        files: list[DiscoveredMacroFile] = grouped[module_name]
        if len(files) > 1:
            collisions.append((module_name, tuple(files)))
    return tuple(collisions)


def _inventory_from_analyses(
    *,
    macro_files: tuple[DiscoveredMacroFile, ...],
    analyses: dict[str, _MacroModuleAnalysis],
) -> StaticMacroInventory:
    exports: dict[str, StaticMacroExport] = {}
    collided_names: set[str] = set()
    faults: list[StaticMacroFault] = []
    for macro_file in macro_files:
        analysis: _MacroModuleAnalysis = analyses[_macro_module_name(macro_file)]
        for statement in analysis.tree.body:
            if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if statement.name.startswith("_"):
                continue
            item: StaticMacroExport = _static_macro_export(
                macro_file=macro_file, analysis=analysis, statement=statement
            )
            existing: StaticMacroExport | None = exports.pop(item.name, None)
            if existing is not None:
                collided_names.add(item.name)
                faults.append(
                    StaticMacroFault(
                        relative_path=item.relative_path,
                        message=(
                            f"Macro name collision for '{item.name}': "
                            f"{existing.relative_path} and {item.relative_path}"
                        ),
                    )
                )
            elif item.name in collided_names:
                faults.append(
                    StaticMacroFault(
                        relative_path=item.relative_path,
                        message=f"Macro name collision for '{item.name}' at {item.relative_path}",
                    )
                )
            else:
                exports[item.name] = item
    return StaticMacroInventory(
        exports=tuple(
            sorted(exports.values(), key=lambda item: (item.name, item.relative_path.as_posix()))
        ),
        faults=tuple(faults),
    )


def _static_macro_export(
    *,
    macro_file: DiscoveredMacroFile,
    analysis: _MacroModuleAnalysis,
    statement: ast.FunctionDef | ast.AsyncFunctionDef,
) -> StaticMacroExport:
    arguments: ast.arguments = statement.args
    return StaticMacroExport(
        name=statement.name,
        relative_path=macro_file.relative_path,
        parameters=tuple(argument.arg for argument in (*arguments.posonlyargs, *arguments.args))
        + ((arguments.vararg.arg,) if arguments.vararg is not None else ())
        + tuple(argument.arg for argument in arguments.kwonlyargs)
        + ((arguments.kwarg.arg,) if arguments.kwarg is not None else ()),
        line=statement.lineno,
        source_digest=hashlib.sha256(macro_file.contents.encode()).hexdigest(),
        dependencies=analysis.dependencies[statement.name],
    )


def _deduplicated_macro_faults(
    faults: tuple[StaticMacroFault, ...],
) -> tuple[StaticMacroFault, ...]:
    return tuple(dict.fromkeys(faults))


def _macro_module_name(macro_file: DiscoveredMacroFile) -> str:
    return ".".join(macro_file.relative_path.with_suffix("").parts)


def _parse_macro_module(*, macro_file: DiscoveredMacroFile) -> ast.Module:
    try:
        module_ast: ast.Module = ast.parse(macro_file.contents, filename=str(macro_file.file_path))
    except SyntaxError as error:
        raise CompileInputError(
            f"Failed to parse macros from '{macro_file.file_path}': {error}"
        ) from error

    for statement in module_ast.body:
        public_declaration_name: str | None = _public_non_function_declaration_name(statement)
        if public_declaration_name is not None:
            raise CompileInputError(
                f"Macro module '{macro_file.relative_path}' declaration "
                f"'{public_declaration_name}' must be underscore-private"
            )
    return module_ast


def _analyze_project_macro_modules(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> dict[str, _MacroModuleAnalysis]:
    """Analyze every authored module and dependency edge before executing any of them."""

    inputs: _MacroAnalysisInputs = _macro_analysis_inputs(macro_files=macro_files)
    analyses: dict[str, _MacroModuleAnalysis] = {
        module_name: _analyze_macro_module(module_name=module_name, inputs=inputs)
        for module_name in inputs.trees
    }
    return _validated_macro_analyses(analyses=analyses)


def _analyze_macro_module(
    *, module_name: str, inputs: _MacroAnalysisInputs
) -> _MacroModuleAnalysis:
    tree: ast.Module = inputs.trees[module_name]
    file: DiscoveredMacroFile = inputs.files[module_name]
    _validate_no_nested_project_imports(
        tree=tree,
        module_name=module_name,
        file=file,
        module_names=inputs.module_names,
        package_names=inputs.package_names,
    )
    imported, module_dependencies = _analyze_macro_imports(
        tree=tree, module_name=module_name, inputs=inputs
    )
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        statement.name: statement
        for statement in tree.body
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    shadowed_imports: set[str] = set(functions).intersection(imported)
    if shadowed_imports:
        shadowed_name: str = sorted(shadowed_imports)[0]
        raise CompileInputError(
            f"Macro module '{file.relative_path}' defines function '{shadowed_name}' over an "
            "imported macro binding; imported macros must not be replaced"
        )
    direct_dependencies, helper_calls, runtime_node_ids = _analyze_macro_calls(
        functions=functions, imported=imported, file=file
    )
    _validate_local_call_cycles(
        exports=inputs.exports[module_name], helper_calls=helper_calls, file=file
    )
    _validate_call_use_locations(
        tree=tree,
        imported=imported,
        local_functions=frozenset(functions),
        runtime_node_ids=runtime_node_ids,
        file=file,
    )
    return _MacroModuleAnalysis(
        file=file,
        name=module_name,
        tree=tree,
        exports=tuple(sorted(inputs.exports[module_name])),
        dependencies=_export_dependencies(
            exports=inputs.exports[module_name],
            direct_dependencies=direct_dependencies,
            helper_calls=helper_calls,
        ),
        module_dependencies=module_dependencies,
    )


def _macro_analysis_inputs(*, macro_files: tuple[DiscoveredMacroFile, ...]) -> _MacroAnalysisInputs:
    files: dict[str, DiscoveredMacroFile] = {}
    for item in macro_files:
        module_name: str = _macro_module_name(item)
        existing: DiscoveredMacroFile | None = files.get(module_name)
        if existing is not None:
            raise CompileInputError(
                f"Macro module path collision for '{module_name}': "
                f"{existing.relative_path} and {item.relative_path}"
            )
        files[module_name] = item
    trees: dict[str, ast.Module] = {
        name: _parse_macro_module(macro_file=item) for name, item in files.items()
    }
    exports: dict[str, frozenset[str]] = {
        name: _module_exports(tree=tree) for name, tree in trees.items()
    }
    return _MacroAnalysisInputs(
        files=files,
        trees=trees,
        exports=exports,
        module_names=frozenset(files),
        package_names=frozenset(_macro_package_name(file) for file in files.values()),
    )


def _module_exports(*, tree: ast.Module) -> frozenset[str]:
    exports: set[str] = set()
    for statement in tree.body:
        if isinstance(
            statement, ast.FunctionDef | ast.AsyncFunctionDef
        ) and not statement.name.startswith("_"):
            exports.add(statement.name)
    return frozenset(exports)


def _analyze_macro_imports(
    *,
    tree: ast.Module,
    module_name: str,
    inputs: _MacroAnalysisInputs,
) -> tuple[dict[str, DeclarationIdentity], tuple[str, ...]]:
    imported: dict[str, DeclarationIdentity] = {}
    module_dependencies: list[str] = []
    file: DiscoveredMacroFile = inputs.files[module_name]
    for statement in tree.body:
        if isinstance(statement, ast.Import):
            local_names: list[str] = [
                name
                for name in _imported_module_names(
                    statement=statement, current_module_name=module_name
                )
                if _is_project_macro_import(
                    imported_name=name,
                    module_names=inputs.module_names,
                    package_names=inputs.package_names,
                )
            ]
            if local_names:
                raise CompileInputError(
                    f"Macro module '{file.relative_path}' must use 'from ... import ...' for "
                    "project macro imports; module imports are not supported"
                )
            continue
        if not isinstance(statement, ast.ImportFrom):
            continue
        resolved_module: str = _resolve_import_from_module(
            statement=statement, current_module_name=module_name
        )
        if resolved_module not in inputs.files:
            if _is_project_macro_import(
                imported_name=resolved_module,
                module_names=inputs.module_names,
                package_names=inputs.package_names,
            ):
                raise CompileInputError(
                    f"Macro module '{file.relative_path}' imports project package "
                    f"'{resolved_module}' instead of a macro module"
                )
            continue
        module_dependencies.append(resolved_module)
        imported = _record_imported_macro_bindings(
            statement=statement,
            importer=file,
            imported_file=inputs.files[resolved_module],
            exported_names=inputs.exports[resolved_module],
            imported=imported,
            resolved_module=resolved_module,
        )
    return imported, tuple(dict.fromkeys(module_dependencies))


def _record_imported_macro_bindings(
    *,
    statement: ast.ImportFrom,
    importer: DiscoveredMacroFile,
    imported_file: DiscoveredMacroFile,
    exported_names: frozenset[str],
    imported: dict[str, DeclarationIdentity],
    resolved_module: str,
) -> dict[str, DeclarationIdentity]:
    updated: dict[str, DeclarationIdentity] = dict(imported)
    for alias in statement.names:
        if alias.name == _STAR_IMPORT_NAME:
            raise CompileInputError(
                f"Macro module '{importer.relative_path}' must not use star imports for project "
                "macros"
            )
        if alias.name not in exported_names:
            raise CompileInputError(
                f"Macro module '{importer.relative_path}' cannot import '{alias.name}' from "
                f"project macro module '{resolved_module}'; the name is not an exported macro"
            )
        _validate_macro_import_visibility(
            importer=importer, imported=imported_file, name=alias.name
        )
        binding: str = alias.asname or alias.name
        if binding in updated:
            raise CompileInputError(
                f"Macro module '{importer.relative_path}' binds project macro import '{binding}' "
                "more than once"
            )
        updated[binding] = DeclarationIdentity(DeclarationKind.MACRO, alias.name)
    return updated


def _analyze_macro_calls(
    *,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    imported: dict[str, DeclarationIdentity],
    file: DiscoveredMacroFile,
) -> tuple[
    dict[str, tuple[DeclarationIdentity, ...]],
    dict[str, tuple[str, ...]],
    frozenset[int],
]:
    direct_dependencies: dict[str, tuple[DeclarationIdentity, ...]] = {}
    helper_calls: dict[str, tuple[str, ...]] = {}
    runtime_node_ids: set[int] = set()
    for function_name, function in functions.items():
        runtime_nodes: tuple[ast.AST, ...] = _runtime_function_nodes(function=function)
        runtime_node_ids.update(id(node) for node in runtime_nodes)
        dependencies, called_helpers = _analyze_function_calls(
            function=function,
            runtime_nodes=runtime_nodes,
            functions=frozenset(functions),
            imported=imported,
            file=file,
        )
        direct_dependencies[function_name] = dependencies
        helper_calls[function_name] = called_helpers
    return direct_dependencies, helper_calls, frozenset(runtime_node_ids)


def _analyze_function_calls(
    *,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    runtime_nodes: tuple[ast.AST, ...],
    functions: frozenset[str],
    imported: dict[str, DeclarationIdentity],
    file: DiscoveredMacroFile,
) -> tuple[tuple[DeclarationIdentity, ...], tuple[str, ...]]:
    bound_names: set[str] = _function_bound_names(function=function, runtime_nodes=runtime_nodes)
    shadowed_imports: set[str] = bound_names.intersection(imported)
    if shadowed_imports:
        shadowed_name: str = sorted(shadowed_imports)[0]
        raise CompileInputError(
            f"Macro module '{file.relative_path}' shadows imported macro '{shadowed_name}'; "
            "imported macros must be called directly without shadowing"
        )
    dependencies: list[DeclarationIdentity] = []
    called_helpers: list[str] = []
    direct_call_nodes: set[int] = {
        id(node.func)
        for node in runtime_nodes
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    for node in runtime_nodes:
        if isinstance(node, ast.Name) and node.id in imported and id(node) not in direct_call_nodes:
            raise CompileInputError(
                f"Macro module '{file.relative_path}' uses imported macro '{node.id}' "
                "dynamically; call imported macros directly"
            )
        if (
            isinstance(node, ast.Name)
            and node.id in functions
            and id(node) not in direct_call_nodes
        ):
            raise CompileInputError(
                f"Macro module '{file.relative_path}' uses local helper '{node.id}' dynamically; "
                "call local macros and helpers directly"
            )
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id in imported:
            dependencies.append(imported[node.func.id])
        elif node.func.id in functions:
            if node.func.id in bound_names:
                raise CompileInputError(
                    f"Macro module '{file.relative_path}' shadows local helper '{node.func.id}'; "
                    "static macro dependency analysis cannot resolve this call"
                )
            called_helpers.append(node.func.id)
    return tuple(dict.fromkeys(dependencies)), tuple(dict.fromkeys(called_helpers))


def _function_bound_names(
    *, function: ast.FunctionDef | ast.AsyncFunctionDef, runtime_nodes: tuple[ast.AST, ...]
) -> set[str]:
    names: set[str] = {
        argument.arg
        for argument in (
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        )
    }
    if function.args.vararg is not None:
        names.add(function.args.vararg.arg)
    if function.args.kwarg is not None:
        names.add(function.args.kwarg.arg)
    names.update(
        node.id
        for node in runtime_nodes
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    )
    return names


def _validate_call_use_locations(
    *,
    tree: ast.Module,
    imported: dict[str, DeclarationIdentity],
    local_functions: frozenset[str],
    runtime_node_ids: frozenset[int],
    file: DiscoveredMacroFile,
) -> None:
    unsupported: ast.Name | None = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id in imported
            and id(node) not in runtime_node_ids
        ),
        None,
    )
    if unsupported is not None:
        raise CompileInputError(
            f"Macro module '{file.relative_path}' uses imported macro '{unsupported.id}' outside "
            "an ordinary function body; call imported macros directly from module-level macro or "
            "helper functions"
        )
    unsupported_local: ast.Name | None = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and node.id in local_functions
            and id(node) not in runtime_node_ids
        ),
        None,
    )
    if unsupported_local is not None:
        raise CompileInputError(
            f"Macro module '{file.relative_path}' uses local helper "
            f"'{unsupported_local.id}' outside an ordinary function body; call local macros and "
            "helpers directly from module-level macro or helper functions"
        )


def _macro_package_name(file: DiscoveredMacroFile) -> str:
    root: Path = file.declaration_root or Path(file.relative_path.parts[0])
    return ".".join(root.parts)


def _runtime_function_nodes(
    *, function: ast.FunctionDef | ast.AsyncFunctionDef
) -> tuple[ast.AST, ...]:
    """Return function-body nodes without entering dynamically nested scopes."""

    nodes: list[ast.AST] = []
    pending: list[ast.AST] = list(reversed(function.body))
    while pending:
        node: ast.AST = pending.pop()
        nodes.append(node)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef):
            continue
        pending.extend(reversed(tuple(ast.iter_child_nodes(node))))
    return tuple(nodes)


def _export_dependencies(
    *,
    exports: frozenset[str],
    direct_dependencies: dict[str, tuple[DeclarationIdentity, ...]],
    helper_calls: dict[str, tuple[str, ...]],
) -> dict[str, tuple[DeclarationIdentity, ...]]:
    dependencies: dict[str, tuple[DeclarationIdentity, ...]] = {}
    for export in exports:
        found: list[DeclarationIdentity] = []
        pending: list[str] = [export]
        visited: set[str] = set()
        while pending:
            function_name: str = pending.pop(0)
            if function_name in visited:
                continue
            visited.add(function_name)
            found.extend(direct_dependencies[function_name])
            for called_function in helper_calls[function_name]:
                if called_function in exports:
                    found.append(DeclarationIdentity(DeclarationKind.MACRO, called_function))
                pending.append(called_function)
        dependencies[export] = tuple(dict.fromkeys(found))
    return dependencies


def _validate_local_call_cycles(
    *,
    exports: frozenset[str],
    helper_calls: dict[str, tuple[str, ...]],
    file: DiscoveredMacroFile,
) -> None:
    completed: frozenset[str] = frozenset()
    for export in sorted(exports):
        completed = _visit_local_call(
            name=export,
            helper_calls=helper_calls,
            file=file,
            active=(),
            completed=completed,
        )


def _visit_local_call(
    *,
    name: str,
    helper_calls: dict[str, tuple[str, ...]],
    file: DiscoveredMacroFile,
    active: tuple[str, ...],
    completed: frozenset[str],
) -> frozenset[str]:
    if name in active:
        cycle: tuple[str, ...] = (*active[active.index(name) :], name)
        raise CompileInputError(f"Macro call cycle in '{file.relative_path}': {' -> '.join(cycle)}")
    if name in completed:
        return completed
    updated: frozenset[str] = completed
    for dependency in helper_calls[name]:
        updated = _visit_local_call(
            name=dependency,
            helper_calls=helper_calls,
            file=file,
            active=(*active, name),
            completed=updated,
        )
    return updated.union((name,))


def _validated_macro_analyses(
    *, analyses: dict[str, _MacroModuleAnalysis]
) -> dict[str, _MacroModuleAnalysis]:
    _validate_import_cycles(analyses=analyses)
    return analyses


def _resolve_import_from_module(*, statement: ast.ImportFrom, current_module_name: str) -> str:
    base: str = statement.module or ""
    if not statement.level:
        return base
    package_parts: list[str] = current_module_name.split(".")[:-1]
    if statement.level > len(package_parts):
        raise CompileInputError(
            f"Relative project macro import in '{current_module_name}' escapes its top-level "
            "package"
        )
    retained: int = len(package_parts) - statement.level + 1
    parts: list[str] = package_parts[: max(retained, 0)]
    if base:
        parts.extend(base.split("."))
    return ".".join(parts)


def _validate_no_nested_project_imports(
    *,
    tree: ast.Module,
    module_name: str,
    file: DiscoveredMacroFile,
    module_names: frozenset[str],
    package_names: frozenset[str],
) -> None:
    top_level_imports: set[ast.Import | ast.ImportFrom] = {
        statement for statement in tree.body if isinstance(statement, ast.Import | ast.ImportFrom)
    }
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom) or node in top_level_imports:
            continue
        imported_names: tuple[str, ...] = _imported_module_names(
            statement=node, current_module_name=module_name
        )
        if any(
            _is_project_macro_import(
                imported_name=name,
                module_names=module_names,
                package_names=package_names,
            )
            for name in imported_names
        ):
            raise CompileInputError(
                f"Macro module '{file.relative_path}' contains a nested project macro import; "
                "project macro imports must be static and module-level"
            )


def _validate_macro_import_visibility(
    *, importer: DiscoveredMacroFile, imported: DiscoveredMacroFile, name: str
) -> None:
    visible: bool = imported.scope_kind is ScopeKind.GLOBAL
    importer_parent: Path = importer.owning_path or importer.relative_path.parent
    owner: Path = imported.owning_path or Path(".")
    if imported.scope_kind is ScopeKind.LOCAL:
        visible = importer_parent == owner
    elif imported.scope_kind is ScopeKind.INHERITED:
        visible = importer_parent == owner or owner in importer_parent.parents
    if not visible:
        raise CompileInputError(
            f"Macro module '{importer.relative_path}' cannot import macro '{name}' from "
            f"'{imported.relative_path}': the imported macro is not visible from the importer scope"
        )


def _validate_import_cycles(*, analyses: dict[str, _MacroModuleAnalysis]) -> None:
    completed: frozenset[str] = frozenset()
    for name in sorted(analyses):
        completed = _visit_macro_import(
            name=name, analyses=analyses, active=(), completed=completed
        )


def _visit_macro_import(
    *,
    name: str,
    analyses: dict[str, _MacroModuleAnalysis],
    active: tuple[str, ...],
    completed: frozenset[str],
) -> frozenset[str]:
    if name in active:
        cycle: tuple[str, ...] = (*active[active.index(name) :], name)
        raise CompileInputError(
            f"Macro import cycle in '{analyses[name].file.relative_path}': {' -> '.join(cycle)}"
        )
    if name in completed:
        return completed
    updated: frozenset[str] = completed
    for dependency in analyses[name].module_dependencies:
        updated = _visit_macro_import(
            name=dependency,
            analyses=analyses,
            active=(*active, name),
            completed=updated,
        )
    return updated.union((name,))


def _load_macro_modules(*, analyses: dict[str, _MacroModuleAnalysis]) -> dict[str, ModuleType]:
    with _MACRO_MODULE_LOAD_LOCK:
        return _load_macro_modules_locked(analyses=analyses)


def _load_macro_modules_locked(
    *, analyses: dict[str, _MacroModuleAnalysis]
) -> dict[str, ModuleType]:
    digest: str = hashlib.sha256(
        "\0".join(
            f"{name}\0{analyses[name].file.file_path}\0{analyses[name].file.contents}"
            for name in sorted(analyses)
        ).encode()
    ).hexdigest()[:16]
    root: str = f"{_SYNTHETIC_PACKAGE_PREFIX}{digest}"
    synthetic_names: list[str] = []
    previous_modules: dict[str, ModuleType] = {}
    modules: dict[str, ModuleType] = {}
    try:
        package_names: set[str] = {root}
        for name in analyses:
            parts: list[str] = name.split(".")[:-1]
            package_names.update(
                f"{root}.{'/'.join(parts[:index]).replace('/', '.')}"
                for index in range(1, len(parts) + 1)
            )
        for package_name in sorted(package_names, key=lambda item: item.count(".")):
            package: ModuleType = ModuleType(package_name)
            package.__package__ = package_name
            package.__path__ = []  # type: ignore[attr-defined]
            previous: ModuleType | None = sys.modules.get(package_name)
            if previous is not None:
                previous_modules[package_name] = previous
            sys.modules[package_name] = package
            synthetic_names.append(package_name)

        remaining_dependencies: dict[str, int] = {
            name: len(analysis.module_dependencies) for name, analysis in analyses.items()
        }
        dependents: dict[str, list[str]] = {}
        for name, analysis in analyses.items():
            for dependency in analysis.module_dependencies:
                dependents.setdefault(dependency, []).append(name)
        ready: list[str] = [
            name
            for name, dependency_count in remaining_dependencies.items()
            if dependency_count == 0
        ]
        heapq.heapify(ready)
        while ready:
            name: str = heapq.heappop(ready)
            analysis: _MacroModuleAnalysis = analyses[name]
            synthetic_name: str = f"{root}.{name}"
            module: ModuleType = ModuleType(synthetic_name)
            module.__file__ = str(analysis.file.file_path)
            module.__package__ = synthetic_name.rpartition(".")[0]
            tree: ast.Module = _rewrite_absolute_project_imports(
                tree=analysis.tree, module_names=frozenset(analyses), root=root
            )
            previous = sys.modules.get(synthetic_name)
            if previous is not None:
                previous_modules[synthetic_name] = previous
            sys.modules[synthetic_name] = module
            synthetic_names.append(synthetic_name)
            try:
                exec(compile(tree, str(analysis.file.file_path), "exec"), module.__dict__)
            except Exception as error:
                raise CompileInputError(
                    f"Failed to load macros from '{analysis.file.file_path}': {error}"
                ) from error
            modules[name] = module
            for dependent in dependents.get(name, ()):
                remaining_dependencies[dependent] -= 1
                if remaining_dependencies[dependent] == 0:
                    heapq.heappush(ready, dependent)
        return modules
    finally:
        for synthetic_name in reversed(synthetic_names):
            previous = previous_modules.get(synthetic_name)
            if previous is None:
                sys.modules.pop(synthetic_name, None)
            else:
                sys.modules[synthetic_name] = previous


def _rewrite_absolute_project_imports(
    *, tree: ast.Module, module_names: frozenset[str], root: str
) -> ast.Module:
    """Retarget module-level project imports; analysis already rejects nested ones."""

    body: list[ast.stmt] = []
    statement: ast.stmt
    for statement in tree.body:
        if (
            isinstance(statement, ast.ImportFrom)
            and statement.level == 0
            and statement.module in module_names
        ):
            body.append(
                ast.copy_location(
                    ast.ImportFrom(
                        module=f"{root}.{statement.module}", names=statement.names, level=0
                    ),
                    statement,
                )
            )
        else:
            body.append(statement)
    return ast.Module(body=body, type_ignores=tree.type_ignores)


def _matches_macro_module(*, imported_name: str, module_names: frozenset[str]) -> bool:
    module_name: str
    for module_name in module_names:
        if module_name == imported_name or module_name.startswith(f"{imported_name}."):
            return True
    return False


def _is_project_macro_import(
    *,
    imported_name: str,
    module_names: frozenset[str],
    package_names: frozenset[str],
) -> bool:
    return _matches_macro_module(imported_name=imported_name, module_names=module_names) or any(
        imported_name == package or imported_name.startswith(f"{package}.")
        for package in package_names
    )


def _imported_module_names(*, statement: ast.stmt, current_module_name: str) -> tuple[str, ...]:
    if isinstance(statement, ast.Import):
        return tuple(alias.name for alias in statement.names)
    if not isinstance(statement, ast.ImportFrom):
        return ()

    base_module_name: str = statement.module or ""
    if statement.level:
        current_package_parts: list[str] = current_module_name.split(".")[:-1]
        retained_part_count: int = len(current_package_parts) - statement.level + 1
        base_parts: list[str] = current_package_parts[: max(retained_part_count, 0)]
        if base_module_name:
            base_parts.extend(base_module_name.split("."))
        base_module_name = ".".join(base_parts)
    names: list[str] = []
    if base_module_name:
        names.append(base_module_name)
    alias: ast.alias
    for alias in statement.names:
        if alias.name == _STAR_IMPORT_NAME:
            continue
        imported_parts: list[str] = [base_module_name] if base_module_name else []
        imported_parts.append(alias.name)
        names.append(".".join(imported_parts))
    return tuple(names)


def _public_non_function_declaration_name(statement: ast.stmt) -> str | None:
    if isinstance(statement, ast.ClassDef) and not statement.name.startswith("_"):
        return statement.name
    if isinstance(statement, ast.TypeAlias) and isinstance(statement.name, ast.Name):
        return statement.name.id if not statement.name.id.startswith("_") else None
    assignment_names: tuple[str, ...] = ()
    if isinstance(statement, ast.Assign):
        names: list[str] = []
        target: ast.expr
        for target in statement.targets:
            node: ast.AST
            for node in ast.walk(target):
                if isinstance(node, ast.Name):
                    names.append(node.id)
        assignment_names = tuple(names)
    elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
        assignment_names = (statement.target.id,)
    return next((name for name in assignment_names if not name.startswith("_")), None)


def expand_sql_macros(
    *,
    sql: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str] | None = None,
    macro_context: MacroContext,
    declaration_resolver: DeclarationScopeResolver | None = None,
    consumer: ResourceIdentity | DeclarationIdentity | None = None,
) -> str:
    """Expand authored Python macros in one executable SQL string."""

    expanded_sql: str
    expanded_sql, _spans = expand_sql_macros_with_spans(
        sql=sql,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_overrides=macro_overrides,
        macro_context=macro_context,
        declaration_resolver=declaration_resolver,
        consumer=consumer,
    )
    return expanded_sql


def expand_sql_macros_with_spans(
    *,
    sql: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str] | None = None,
    macro_context: MacroContext,
    declaration_resolver: DeclarationScopeResolver | None = None,
    consumer: ResourceIdentity | DeclarationIdentity | None = None,
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    """Expand authored Python macros, returning the span of every substitution."""

    result: MacroExpansionResult = expand_sql_macros_result(
        sql=sql,
        file_path=file_path,
        loaded_macros=loaded_macros,
        macro_overrides=macro_overrides,
        macro_context=macro_context,
        declaration_resolver=declaration_resolver,
        consumer=consumer,
    )
    return result.sql, result.spans


def expand_sql_macros_result(
    *,
    sql: str,
    file_path: Path,
    loaded_macros: dict[str, LoadedMacro],
    macro_overrides: dict[str, str] | None = None,
    macro_context: MacroContext,
    declaration_resolver: DeclarationScopeResolver | None = None,
    declarations: DeclarationResolutionContext | None = None,
    consumer: ResourceIdentity | DeclarationIdentity | None = None,
) -> MacroExpansionResult:
    """Expand macros and retain deterministic resolved dependency facts."""

    if MACRO_TOKEN not in sql:
        return MacroExpansionResult(sql=sql)
    if declarations is None and declaration_resolver is not None:
        from sqlbuild.compiler.compile._helpers.render.declarations import (
            resolve_declaration_context,
        )

        declarations = resolve_declaration_context(
            resolver=declaration_resolver, file_path=file_path
        )
    expansion: _native.NativeMacroExpansion = _native.NativeMacroExpansion(
        file_path,
        (
            loaded_macros,
            {} if macro_overrides is None else macro_overrides,
            macro_context,
            declarations,
            consumer,
        ),
        macro_context._enforce_explicit_references,
        macro_expansion_classes(),
    )
    expanded_sql, spans, argument_references, dependencies, usages = expansion.expand(
        sql, active_macro_bridge()
    )
    return MacroExpansionResult(
        sql=expanded_sql,
        spans=tuple(
            ExpansionSpan(
                source_start=source_start,
                source_end=source_end,
                output_start=output_start,
                output_end=output_end,
            )
            for source_start, source_end, output_start, output_end in spans
        ),
        argument_references=call_site_sql_references(
            tuple(
                SqlResourceRef(kind=SqlResourceRefKind(kind), name=name)
                for kind, name in argument_references
            )
        ),
        dependencies=tuple(dict.fromkeys(dependencies)),
        usages=tuple(dict.fromkeys(usages)),
    )


@cache
def macro_expansion_classes() -> dict[str, object]:
    """The classes, enums and helpers the native expansion builds facts and errors from."""

    from sqlbuild.compiler.frontier.exceptions import NativeStageMismatchError
    from sqlbuild.compiler.frontier.main._report_native_fallback import report_native_fallback
    from sqlbuild.compiler.frontier.types import NativeFallbackSite

    return {
        "compile_error": CompileInputError,
        "macro_argument_error": MacroArgumentError,
        "mismatch_error": NativeStageMismatchError,
        "declaration_identity": DeclarationIdentity,
        "declaration_kind": DeclarationKind,
        "macro_kind": DeclarationKind.MACRO,
        "usage_record": UsageRecord,
        "runtime_usage": UsageKind.RUNTIME,
        "resource_identity": ResourceIdentity,
        "model_kind": ResourceKind.MODEL,
        "resource_ref": SqlResourceRef,
        "ref_kinds": typed_reference_kinds(),
        "ref_functions": {
            kind.value: function for function, kind in typed_reference_kinds().items()
        },
        "store_tokens": macro_store_tokens(),
        "relation_renderer": RELATION_RENDERER,
        "invocation_context": macro_invocation_context,
        "generated": {
            "compiler_diagnostic": CompilerDiagnostic,
            "report_diagnostic": report_compile_diagnostic,
            "source_location": SourceLocation,
            "resource_identity": ResourceIdentity,
            "generic_syntax": SqlLexicalSyntax().native_mapping,
            "generated_help": explicit_references_help(allowed="macro-generated references"),
            "all_markers": list(GENERATED_REFERENCE_MARKERS),
        },
        "report_mocked": partial(
            report_native_fallback, site=NativeFallbackSite.MACRO_CALL_MOCKED, kind="test_mock"
        ),
        "int_type": int,
        "float_type": float,
    }


def _inventory_project_macros(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> StaticMacroInventory:
    """Validate and inventory project macro exports without executing authored code."""

    try:
        analyses: dict[str, _MacroModuleAnalysis] = _analyze_project_macro_modules(
            macro_files=macro_files
        )
    except CompileInputError:
        return _inventory_project_macros_tolerantly(macro_files=macro_files)
    return _inventory_from_analyses(macro_files=macro_files, analyses=analyses)


def find_macro_call_names(sql: str) -> tuple[str, ...]:
    """Return unique authored macro call names in encounter order."""

    return tuple(
        name
        for name in _native_macro_call_names(sql=sql, nested=False)
        if name not in DECLARATION_REFERENCE_NAMES
    )


def _native_macro_call_names(*, sql: str, nested: bool) -> tuple[str, ...]:
    """Every call name Python's scan finds, declaration calls included."""

    names: list[str] | None
    message: str | None
    names, message = _native.macro_call_names(sql, nested)
    if names is None:
        raise CompileInputError(message or "")
    return tuple(names)


def macro_invocation_context(
    *,
    expansion: _native.NativeMacroExpansion,
    declarations: DeclarationResolutionContext | None,
    file_path: Path,
    macro_context: MacroContext,
) -> MacroContext:
    """The context a macro is called with: visible constants and enums that record their reads."""

    if declarations is None:
        return macro_context
    constant_values: Mapping[str, object] = _build_constant_context_values(declarations.constants)
    enum_values: Mapping[str, object] = _build_enum_context_values(
        declarations=declarations.enums, file_path=file_path, on_miss=expansion.block_memo
    )
    constants: Mapping[str, object] = _MacroDeclarationValues(
        values=constant_values,
        inaccessible=declarations.inaccessible_constants,
        declaration_kind="constant",
        file_path=file_path,
        on_access=partial(expansion.declaration_read, DeclarationKind.CONSTANT.value),
        on_miss=expansion.block_memo,
    )
    enum_mapping: Mapping[str, object] = _MacroDeclarationValues(
        values=enum_values,
        inaccessible=declarations.inaccessible_enums,
        declaration_kind="enum",
        file_path=file_path,
        on_access=partial(expansion.declaration_read, DeclarationKind.ENUM.value),
        on_miss=expansion.block_memo,
    )
    return replace(
        macro_context,
        constants=constants,
        enums=cast(Mapping[str, Mapping[str, str | int]], enum_mapping),
        _constant_declarations=MappingProxyType(declarations.constants),
    )


def _build_constant_context_values(
    declarations: Mapping[str, ConstantDeclaration],
) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for name, declaration in declarations.items():
        values[name] = _constant_python_value(declaration.value)
    return MappingProxyType(values)


def _build_enum_context_values(
    *,
    declarations: Mapping[str, EnumDeclaration],
    file_path: Path,
    on_miss: Callable[[], None],
) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for name, declaration in declarations.items():
        members: dict[str, str | int] = {}
        for member in declaration.members:
            members[member.name] = member.value
        values[name] = _MacroEnumMembers(
            enum_name=name,
            values=MappingProxyType(members),
            file_path=file_path,
            on_miss=on_miss,
        )
    return MappingProxyType(values)


def _constant_python_value(value: SqlValue) -> object:
    if value.kind in {
        SqlValueKind.STRING,
        SqlValueKind.INTEGER,
        SqlValueKind.BOOLEAN,
        SqlValueKind.FLOAT,
        SqlValueKind.DECIMAL,
        SqlValueKind.NULL,
    }:
        return value.value
    if value.kind == SqlValueKind.LIST:
        return tuple(_constant_python_value(item) for item in _constant_items(value))
    if value.kind == SqlValueKind.SET:
        return frozenset(_constant_python_value(item) for item in _constant_items(value))
    return MappingProxyType(
        {key: _constant_python_value(item) for key, item in _constant_object_items(value)}
    )


def _constant_items(value: SqlValue) -> tuple[SqlValue, ...]:
    if not isinstance(value.value, tuple) or not all(
        isinstance(item, SqlValue) for item in value.value
    ):
        raise CompileInputError("Invalid normalized collection constant in macro context")
    return cast(tuple[SqlValue, ...], value.value)


def _constant_object_items(value: SqlValue) -> tuple[tuple[str, SqlValue], ...]:
    if not isinstance(value.value, tuple) or not all(
        isinstance(item, tuple)
        and len(item) == _OBJECT_ENTRY_LENGTH
        and isinstance(item[0], str)
        and isinstance(item[1], SqlValue)
        for item in value.value
    ):
        raise CompileInputError("Invalid normalized object constant in macro context")
    return cast(tuple[tuple[str, SqlValue], ...], value.value)
