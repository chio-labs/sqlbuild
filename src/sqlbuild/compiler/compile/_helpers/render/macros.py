"""Compile-time expansion helpers for authored project SQL macros."""

from __future__ import annotations

import ast
import copy
import hashlib
import heapq
import inspect
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from sqlbuild.compiler.compile.constants import (
    DECLARATION_REFERENCE_NAMES,
    MACRO_CONTEXT_PARAMETER_NAME,
    MACRO_TOKEN,
    PYTHON_LITERAL_NAMES,
    SQL_OPEN_PAREN_TOKEN,
    SQL_QUOTE_TOKENS,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
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
from sqlbuild.compiler.discovery.models import DiscoveredMacroFile
from sqlbuild.compiler.resource_names.main._validate_resource_identity import (
    validate_resource_identity,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeKind, UsageKind
from sqlbuild.compiler.sql_analysis.main._find_matching_paren import find_matching_paren
from sqlbuild.compiler.sql_analysis.main._is_identifier_character import (
    is_identifier_character as _is_identifier_continue,
)
from sqlbuild.compiler.sql_analysis.main._is_identifier_start import (
    is_identifier_start as _is_identifier_start,
)
from sqlbuild.compiler.sql_analysis.main._skip_block_comment import skip_block_comment
from sqlbuild.compiler.sql_analysis.main._skip_line_comment import skip_line_comment
from sqlbuild.compiler.sql_analysis.main._skip_quoted_text import skip_quoted_text

_CONTEXT: str = "Macro expansion"
_LINE_COMMENT_TOKEN: str = "--"
_BLOCK_COMMENT_TOKEN: str = "/*"
_STAR_IMPORT_NAME: str = "*"
_MACRO_SCAN_PATTERN: re.Pattern[str] = re.compile(r"@|--|/\*|'|\"|`")
_SYNTHETIC_PACKAGE_PREFIX: str = "_sqlbuild_project_macros_"
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


@dataclass
class _ExpansionFacts:
    dependencies: list[DeclarationIdentity] = field(default_factory=list)
    usages: list[UsageRecord] = field(default_factory=list)

    def add_dependency(self, identity: DeclarationIdentity) -> _ExpansionFacts:
        """Record a resolved dependency in encounter order."""

        self.dependencies.append(identity)
        return self

    def add_usage(self, usage: UsageRecord) -> _ExpansionFacts:
        """Record a resolved macro-to-macro edge in encounter order."""

        self.usages.append(usage)
        return self


@dataclass(frozen=True)
class _ExpansionState:
    loaded_macros: dict[str, LoadedMacro]
    macro_overrides: dict[str, str]
    macro_context: MacroContext
    declaration_resolver: DeclarationScopeResolver | None
    declarations: DeclarationResolutionContext | None
    facts: _ExpansionFacts
    consumer: ResourceIdentity | DeclarationIdentity | None = None


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
    class Rewriter(ast.NodeTransformer):
        def visit_ImportFrom(self, node: ast.ImportFrom) -> ast.ImportFrom:  # noqa: N802
            if node.level == 0 and node.module in module_names:
                return ast.copy_location(
                    ast.ImportFrom(module=f"{root}.{node.module}", names=node.names, level=0),
                    node,
                )
            return node

    return ast.fix_missing_locations(Rewriter().visit(copy.deepcopy(tree)))


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

    facts: _ExpansionFacts = _ExpansionFacts()
    state: _ExpansionState = _ExpansionState(
        loaded_macros=loaded_macros,
        macro_overrides={} if macro_overrides is None else macro_overrides,
        macro_context=macro_context,
        declaration_resolver=declaration_resolver,
        declarations=declarations,
        facts=facts,
        consumer=consumer,
    )
    expanded_sql, spans = _expand_sql_macros(
        sql=sql,
        consumer_path=file_path,
        state=state,
        stack=(),
    )
    return MacroExpansionResult(
        sql=expanded_sql,
        spans=spans,
        dependencies=tuple(dict.fromkeys(facts.dependencies)),
        usages=tuple(dict.fromkeys(facts.usages)),
    )


def _expand_sql_macros(
    *,
    sql: str,
    consumer_path: Path,
    state: _ExpansionState,
    stack: tuple[DeclarationIdentity, ...],
) -> tuple[str, tuple[ExpansionSpan, ...]]:
    if MACRO_TOKEN not in sql:
        return sql, ()

    declarations: DeclarationResolutionContext | None = state.declarations
    if declarations is None and state.declaration_resolver is not None:
        from sqlbuild.compiler.compile._helpers.render.declarations import (
            resolve_declaration_context,
        )

        declarations = resolve_declaration_context(
            resolver=state.declaration_resolver, file_path=consumer_path
        )

    rendered_sql_parts: list[str] = []
    spans: list[ExpansionSpan] = []
    output_length: int = 0
    cursor: int = 0
    while cursor < len(sql):
        macro_start_index: int | None = _find_next_macro_start(sql=sql, start_index=cursor)
        if macro_start_index is None:
            rendered_sql_parts.append(sql[cursor:])
            break
        leading_literal: str = sql[cursor:macro_start_index]
        rendered_sql_parts.append(leading_literal)
        output_length += len(leading_literal)
        macro_result: object
        next_index: int
        macro_result, next_index = _evaluate_macro_call(
            sql=sql,
            call_start_index=macro_start_index,
            file_path=consumer_path,
            state=state,
            declarations=declarations,
            stack=stack,
            top_level=True,
        )
        if not isinstance(macro_result, str):
            raise CompileInputError(
                f"Macro '@{_parse_macro_name(sql=sql, call_start_index=macro_start_index)}' in "
                f"'{consumer_path}' must return a SQL string when used directly in SQL"
            )
        rendered_sql_parts.append(macro_result)
        spans.append(
            ExpansionSpan(
                source_start=macro_start_index,
                source_end=next_index,
                output_start=output_length,
                output_end=output_length + len(macro_result),
            )
        )
        output_length += len(macro_result)
        cursor = next_index
    return "".join(rendered_sql_parts), tuple(spans)


def find_macro_call_names(sql: str) -> tuple[str, ...]:
    """Return unique authored macro call names in encounter order."""

    return tuple(
        name for name in _find_sqlbuild_call_names(sql) if name not in DECLARATION_REFERENCE_NAMES
    )


def _find_sqlbuild_call_names(sql: str) -> tuple[str, ...]:
    """Return executable SQLBuild call names, excluding quoted and commented text."""

    if MACRO_TOKEN not in sql:
        return ()

    names: list[str] = []
    seen: set[str] = set()
    cursor: int = 0
    while cursor < len(sql):
        macro_start_index: int | None = _find_next_macro_start(sql=sql, start_index=cursor)
        if macro_start_index is None:
            break
        macro_name: str = _parse_macro_name(sql=sql, call_start_index=macro_start_index)
        if macro_name not in seen:
            seen.add(macro_name)
            names.append(macro_name)
        opening_paren_index: int = _skip_whitespace(
            sql=sql, start_index=macro_start_index + 1 + len(macro_name)
        )
        cursor = _find_matching_paren(sql=sql, opening_paren_index=opening_paren_index) + 1
    return tuple(names)


def _evaluate_macro_call(
    *,
    sql: str,
    call_start_index: int,
    file_path: Path,
    state: _ExpansionState,
    declarations: DeclarationResolutionContext | None,
    stack: tuple[DeclarationIdentity, ...],
    top_level: bool,
) -> tuple[object, int]:
    macro_name: str = _parse_macro_name(sql=sql, call_start_index=call_start_index)
    loaded_macro: LoadedMacro | None = (
        declarations.macros.get(macro_name)
        if declarations is not None
        else state.loaded_macros.get(macro_name)
    )
    override_value: str | None = state.macro_overrides.get(macro_name)
    if declarations is not None and macro_name in declarations.inaccessible_macros:
        record: DeclarationRecord = declarations.inaccessible_macros[macro_name]
        suggestions: str = ", ".join(sorted(declarations.macros)) or "none"
        owner: str = record.owning_path or "global"
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' is inaccessible. Defined at "
            f"'{record.path}:{record.line}:{record.column}' with scope owner '{owner}'; "
            f"consumer/definition path is '{file_path}'. Visible macros: {suggestions}"
        )
    if loaded_macro is None:
        available: object = declarations.macros if declarations is not None else state.loaded_macros
        available_macro_names: str = ", ".join(sorted(available)) or "none"
        raise CompileInputError(
            f"Unknown macro '@{macro_name}' in '{file_path}'. Available macros: "
            f"{available_macro_names}"
        )
    opening_paren_index: int = _skip_whitespace(
        sql=sql, start_index=call_start_index + 1 + len(macro_name)
    )
    closing_paren_index: int = _find_matching_paren(
        sql=sql, opening_paren_index=opening_paren_index
    )
    if override_value is not None:
        _validate_final_macro_sql(
            macro_name=macro_name, file_path=file_path, macro_result=override_value
        )
        return override_value, closing_paren_index + 1
    identity: DeclarationIdentity = (
        declarations.macro_records[macro_name].identity
        if declarations is not None
        else DeclarationIdentity(kind=DeclarationKind.MACRO, name=macro_name)
    )
    if identity in stack:
        cycle: tuple[DeclarationIdentity, ...] = (*stack[stack.index(identity) :], identity)
        chain: str = " -> ".join(item.name for item in cycle)
        paths: str = " -> ".join(
            str(state.loaded_macros[item.name].relative_path) for item in cycle
        )
        raise CompileInputError(
            f"Macro expansion cycle detected: {chain}. Definition paths: {paths}"
        )
    _ = state.facts.add_dependency(identity)
    if stack:
        _ = state.facts.add_usage(
            UsageRecord(stack[-1], identity, UsageKind.DECLARATION_DEPENDENCY),
        )
    elif state.consumer is not None:
        _ = state.facts.add_usage(UsageRecord(state.consumer, identity, UsageKind.RUNTIME))
    args_source: str = sql[opening_paren_index + 1 : closing_paren_index]
    args: tuple[object, ...]
    kwargs: dict[str, object]
    args, kwargs = _parse_macro_arguments(
        args_source=args_source,
        file_path=file_path,
        state=state,
        declarations=declarations,
        stack=stack,
    )
    try:
        macro_result: object = _call_loaded_macro(
            loaded_macro=loaded_macro,
            macro_context=state.macro_context,
            args=args,
            kwargs=kwargs,
        )
    except TypeError as error:
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' could not be called: {error}"
        ) from error
    except Exception as error:
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' failed: {error}"
        ) from error
    if top_level and not isinstance(macro_result, str):
        raise CompileInputError(
            f"Macro '@{macro_name}' in '{file_path}' must return a SQL string when "
            "used directly in SQL"
        )
    if isinstance(macro_result, str):
        _validate_final_macro_sql(
            macro_name=macro_name, file_path=file_path, macro_result=macro_result
        )
    return macro_result, closing_paren_index + 1


def _validate_final_macro_sql(*, macro_name: str, file_path: Path, macro_result: str) -> None:
    generated_calls: tuple[str, ...] = _find_sqlbuild_call_names(macro_result)
    if not generated_calls:
        return
    calls: str = ", ".join(f"@{name}()" for name in generated_calls)
    raise CompileInputError(
        f"Macro '@{macro_name}' in '{file_path}' returned SQLBuild call(s) {calls}. "
        "Macro output must be final SQL. Compose macros with ordinary Python imports and "
        "function calls instead; nested @macro() calls are supported only when explicitly "
        "authored in SQL"
    )


def _call_loaded_macro(
    *,
    loaded_macro: LoadedMacro,
    macro_context: MacroContext,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> object:
    signature: inspect.Signature = inspect.signature(loaded_macro.function)
    parameters: tuple[inspect.Parameter, ...] = tuple(signature.parameters.values())
    if (
        parameters
        and parameters[0].kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        and parameters[0].name == MACRO_CONTEXT_PARAMETER_NAME
    ):
        if MACRO_CONTEXT_PARAMETER_NAME in kwargs:
            raise CompileInputError(
                f"Macro '@{loaded_macro.name}' must not be called with keyword argument 'ctx'; "
                "'ctx' is reserved for injected macro context"
            )
        return loaded_macro.function(macro_context, *args, **kwargs)
    return loaded_macro.function(*args, **kwargs)


def _parse_macro_arguments(
    *,
    args_source: str,
    file_path: Path,
    state: _ExpansionState,
    declarations: DeclarationResolutionContext | None,
    stack: tuple[DeclarationIdentity, ...],
) -> tuple[tuple[object, ...], dict[str, object]]:
    if not args_source.strip():
        return (), {}
    rewritten_args_source: str
    placeholder_values: dict[str, object]
    rewritten_args_source, placeholder_values = _rewrite_nested_macro_calls(
        args_source=args_source,
        file_path=file_path,
        state=state,
        declarations=declarations,
        stack=stack,
    )
    try:
        expression: ast.Expression = ast.parse(f"_macro_call({rewritten_args_source})", mode="eval")
    except SyntaxError as error:
        raise CompileInputError(
            f"Macro arguments in '{file_path}' could not be parsed: {error}"
        ) from error
    if not isinstance(expression.body, ast.Call):
        raise CompileInputError(f"Macro arguments in '{file_path}' could not be parsed")
    call_expression: ast.Call = expression.body
    args: tuple[object, ...] = tuple(
        _evaluate_literal_ast_node(
            node=argument,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        for argument in call_expression.args
    )
    kwargs: dict[str, object] = {}
    keyword: ast.keyword
    for keyword in call_expression.keywords:
        if keyword.arg is None:
            raise CompileInputError(
                f"Macro arguments in '{file_path}' must not use **kwargs expansion syntax"
            )
        kwargs[keyword.arg] = _evaluate_literal_ast_node(
            node=keyword.value,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
    return args, kwargs


def _rewrite_nested_macro_calls(
    *,
    args_source: str,
    file_path: Path,
    state: _ExpansionState,
    declarations: DeclarationResolutionContext | None,
    stack: tuple[DeclarationIdentity, ...],
) -> tuple[str, dict[str, object]]:
    rewritten_parts: list[str] = []
    placeholder_values: dict[str, object] = {}
    cursor: int = 0
    replacement_index: int = 0
    while cursor < len(args_source):
        macro_start_index: int | None = _find_next_macro_start(sql=args_source, start_index=cursor)
        if macro_start_index is None:
            rewritten_parts.append(args_source[cursor:])
            break
        rewritten_parts.append(args_source[cursor:macro_start_index])
        nested_result: object
        next_index: int
        nested_result, next_index = _evaluate_macro_call(
            sql=args_source,
            call_start_index=macro_start_index,
            file_path=file_path,
            state=state,
            declarations=declarations,
            stack=stack,
            top_level=False,
        )
        placeholder: str = f"__sqlbuild_macro_arg_{replacement_index}"
        replacement_index += 1
        placeholder_values[placeholder] = nested_result
        rewritten_parts.append(placeholder)
        cursor = next_index
    return "".join(rewritten_parts), placeholder_values


def _evaluate_literal_ast_node(
    *,
    node: ast.AST,
    placeholder_values: dict[str, object],
    file_path: Path,
) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in placeholder_values:
            return placeholder_values[node.id]
        if node.id in PYTHON_LITERAL_NAMES:
            return ast.literal_eval(node)
    if isinstance(node, ast.List):
        return [
            _evaluate_literal_ast_node(
                node=element,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for element in node.elts
        ]
    if isinstance(node, ast.Tuple):
        return tuple(
            _evaluate_literal_ast_node(
                node=element,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for element in node.elts
        )
    if isinstance(node, ast.Dict):
        return {
            _evaluate_dict_key_ast_node(
                key_node=key,
                placeholder_values=placeholder_values,
                file_path=file_path,
            ): _evaluate_literal_ast_node(
                node=value,
                placeholder_values=placeholder_values,
                file_path=file_path,
            )
            for key, value in zip(node.keys, node.values, strict=True)
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand: object = _evaluate_literal_ast_node(
            node=node.operand,
            placeholder_values=placeholder_values,
            file_path=file_path,
        )
        if not isinstance(operand, int | float):
            raise CompileInputError(f"Macro arguments in '{file_path}' use unsupported unary value")
        return -operand if isinstance(node.op, ast.USub) else operand
    raise CompileInputError(
        f"Macro arguments in '{file_path}' must use only Python literals and nested macro calls"
    )


def _evaluate_dict_key_ast_node(
    *,
    key_node: ast.AST | None,
    placeholder_values: dict[str, object],
    file_path: Path,
) -> object:
    if key_node is None:
        raise CompileInputError(f"Macro arguments in '{file_path}' must not use dict unpacking")
    return _evaluate_literal_ast_node(
        node=key_node,
        placeholder_values=placeholder_values,
        file_path=file_path,
    )


def _find_next_macro_start(*, sql: str, start_index: int) -> int | None:
    index: int = start_index
    while True:
        match: re.Match[str] | None = _MACRO_SCAN_PATTERN.search(sql, index)
        if match is None:
            return None
        index = match.start()
        token: str = match.group()
        if token in SQL_QUOTE_TOKENS:
            index = skip_quoted_text(sql=sql, start=index, context=_CONTEXT)
            continue
        if token == _LINE_COMMENT_TOKEN:
            index = skip_line_comment(sql=sql, start=index)
            continue
        if token == _BLOCK_COMMENT_TOKEN:
            index = skip_block_comment(sql=sql, start=index, context=_CONTEXT)
            continue
        if _is_macro_call_start(sql=sql, at_index=index):
            return index
        index += 1


def _is_macro_call_start(*, sql: str, at_index: int) -> bool:
    if at_index + 1 >= len(sql) or not _is_identifier_start(sql[at_index + 1]):
        return False
    cursor: int = at_index + 2
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
        cursor = _skip_whitespace(sql=sql, start_index=cursor)
    return cursor < len(sql) and sql[cursor] == SQL_OPEN_PAREN_TOKEN


def _parse_macro_name(*, sql: str, call_start_index: int) -> str:
    cursor: int = call_start_index + 1
    while cursor < len(sql) and _is_identifier_continue(sql[cursor]):
        cursor += 1
    return sql[call_start_index + 1 : cursor]


def _find_matching_paren(*, sql: str, opening_paren_index: int) -> int:
    if opening_paren_index >= len(sql) or sql[opening_paren_index] != SQL_OPEN_PAREN_TOKEN:
        raise CompileInputError("expected opening parenthesis")
    return find_matching_paren(sql=sql, open_paren_index=opening_paren_index, context=_CONTEXT)


def _skip_whitespace(*, sql: str, start_index: int) -> int:
    index: int = start_index
    while index < len(sql) and sql[index].isspace():
        index += 1
    return index
