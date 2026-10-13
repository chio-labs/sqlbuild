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
from sqlbuild._native import explicit_references_help
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
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredMacroFile,
    EnumDeclaration,
)
from sqlbuild.compiler.macro_bridge.constants import (
    GENERATED_REFERENCE_MARKERS,
)
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
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind, UsageKind
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.python_nodes.models import RELATION_RENDERER, SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceLocation
from sqlbuild.sql_values.models import SqlValue
from sqlbuild.sql_values.types import SqlValueKind

_SYNTHETIC_PACKAGE_PREFIX: str = "_sqlbuild_project_macros_"
_OBJECT_ENTRY_LENGTH: int = 2
_MACRO_MODULE_LOAD_LOCK: threading.RLock = threading.RLock()


@dataclass(frozen=True)
class _MacroModuleLoad:
    file: DiscoveredMacroFile
    tree: ast.Module
    module_dependencies: tuple[str, ...]


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
    trees: tuple[ast.Module | str, ...] = tuple(
        _parse_macro_module(macro_file=macro_file) for macro_file in macro_files
    )
    inventory: StaticMacroInventory
    loads: dict[str, _MacroModuleLoad] | None
    inventory, loads = _native_macro_inventory(macro_files=macro_files, trees=trees)
    if inventory.faults or loads is None:
        raise CompileInputError(inventory.faults[0].message)

    modules: dict[str, ModuleType] = _load_macro_modules(analyses=loads)
    export_dependencies: dict[tuple[Path, str], tuple[DeclarationIdentity, ...]] = {
        (item.relative_path, item.name): item.dependencies for item in inventory.exports
    }
    loaded_macros: dict[str, LoadedMacro] = {}
    module_name: str
    load: _MacroModuleLoad
    for module_name, load in loads.items():
        macro_file: DiscoveredMacroFile = load.file
        module: ModuleType = modules[module_name]
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


def _static_macro_export(
    *,
    row: tuple[str, int, list[str], int, str, list[str]],
    macro_files: tuple[DiscoveredMacroFile, ...],
) -> StaticMacroExport:
    name, file_index, parameters, line, source_digest, dependencies = row
    return StaticMacroExport(
        name=name,
        relative_path=macro_files[file_index].relative_path,
        parameters=tuple(parameters),
        line=line,
        source_digest=source_digest,
        dependencies=tuple(
            DeclarationIdentity(DeclarationKind.MACRO, dependency) for dependency in dependencies
        ),
    )


def _parse_macro_module(*, macro_file: DiscoveredMacroFile) -> ast.Module | str:
    """CPython's tree of a macro module, or the message of its syntax error."""

    try:
        return ast.parse(macro_file.contents, filename=str(macro_file.file_path))
    except SyntaxError as error:
        return f"Failed to parse macros from '{macro_file.file_path}': {error}"


def _native_macro_inventory(
    *, macro_files: tuple[DiscoveredMacroFile, ...], trees: tuple[ast.Module | str, ...]
) -> tuple[StaticMacroInventory, dict[str, _MacroModuleLoad] | None]:
    """The native static inventory and, when every module analysed cleanly, the load plan."""

    export_rows, fault_rows, module_rows = _native.inventory_macro_modules(
        [
            (
                str(macro_file.relative_path),
                macro_file.relative_path.as_posix(),
                list(macro_file.relative_path.parts),
                None
                if macro_file.declaration_root is None
                else list(macro_file.declaration_root.parts),
                None if macro_file.owning_path is None else list(macro_file.owning_path.parts),
                macro_file.scope_kind.value,
                macro_file.contents,
                tree if isinstance(tree, str) else None,
            )
            for macro_file, tree in zip(macro_files, trees, strict=True)
        ]
    )
    inventory: StaticMacroInventory = StaticMacroInventory(
        exports=tuple(
            _static_macro_export(row=row, macro_files=macro_files) for row in export_rows
        ),
        faults=tuple(
            StaticMacroFault(relative_path=macro_files[file_index].relative_path, message=message)
            for file_index, message in fault_rows
        ),
    )
    if module_rows is None:
        return inventory, None
    loads: dict[str, _MacroModuleLoad] = {}
    for file_index, module_name, module_dependencies in module_rows:
        tree: ast.Module | str = trees[file_index]
        if isinstance(tree, str):
            raise CompileInputError(tree)
        loads[module_name] = _MacroModuleLoad(
            file=macro_files[file_index],
            tree=tree,
            module_dependencies=tuple(module_dependencies),
        )
    return inventory, loads


def _load_macro_modules(*, analyses: dict[str, _MacroModuleLoad]) -> dict[str, ModuleType]:
    with _MACRO_MODULE_LOAD_LOCK:
        return _load_macro_modules_locked(analyses=analyses)


def _load_macro_modules_locked(*, analyses: dict[str, _MacroModuleLoad]) -> dict[str, ModuleType]:
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
            analysis: _MacroModuleLoad = analyses[name]
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
        "store_tokens": {
            "macro_token": _native.macro_store_token,
            "context_token": _native.context_store_token,
        },
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
        "int_type": int,
        "float_type": float,
    }


def _inventory_project_macros(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> StaticMacroInventory:
    """Validate and inventory project macro exports without executing authored code."""

    inventory: StaticMacroInventory
    inventory, _loads = _native_macro_inventory(
        macro_files=macro_files,
        trees=tuple(_parse_macro_module(macro_file=macro_file) for macro_file in macro_files),
    )
    return inventory


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
