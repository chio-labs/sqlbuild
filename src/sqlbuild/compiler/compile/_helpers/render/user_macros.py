"""Project macro modules loaded and run as user code, and the context user macros read."""

from __future__ import annotations

import ast
import hashlib
import inspect
import sys
import threading
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path
from types import MappingProxyType, ModuleType
from typing import cast

import sqlbuild._native as _native
from sqlbuild._native import (
    ConstantDeclaration,
    DeclarationIdentity,
    DeclarationKind,
    DeclarationRecord,
    DeclarationResolutionContext,
    DiscoveredMacroFile,
    EnumDeclaration,
    LoadedMacro,
    SqlValue,
    SqlValueKind,
    StaticMacroExport,
    StaticMacroFault,
    StaticMacroInventory,
    validate_resource_identity,
)
from sqlbuild.compiler.compile.exceptions import (
    CompileInputError,
    MacroDeclarationLookupError,
)
from sqlbuild.compiler.compile.models import MacroContext

_OBJECT_ENTRY_LENGTH: int = 2
_SQL_SUFFIX: str = ".sql"
_SQL_LANGUAGE: str = "sql"
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

    python_files: tuple[DiscoveredMacroFile, ...] = tuple(
        macro_file for macro_file in macro_files if macro_file.relative_path.suffix != _SQL_SUFFIX
    )
    loaded_macros: dict[str, LoadedMacro] = (
        _load_python_macros(python_files) if python_files else {}
    )
    sql_file: DiscoveredMacroFile
    for sql_file, (name, parameters, calls) in _sql_macro_rows(macro_files):
        validate_resource_identity(name=name, kind="macro", path=sql_file.relative_path)
        existing_macro: LoadedMacro | None = loaded_macros.get(name)
        if existing_macro is not None:
            raise CompileInputError(
                f"Macro name collision for '{name}': "
                f"{existing_macro.file_path} and {sql_file.file_path}"
            )
        loaded_macros[name] = LoadedMacro(
            name=name,
            file_path=sql_file.file_path,
            relative_path=sql_file.relative_path,
            raw_source=sql_file.contents,
            function=_sql_macro_function(name=name, parameters=parameters),
            dependencies=tuple(
                DeclarationIdentity(DeclarationKind.MACRO, called) for called in calls
            ),
            language=_SQL_LANGUAGE,
        )
    return loaded_macros


def _sql_macro_rows(
    macro_files: tuple[DiscoveredMacroFile, ...],
) -> tuple[tuple[DiscoveredMacroFile, tuple[str, list[str], list[str]]], ...]:
    """Each SQL macro file with its parsed `(name, parameters, calls)`, checked natively."""

    sql_files: tuple[DiscoveredMacroFile, ...] = tuple(
        macro_file for macro_file in macro_files if macro_file.relative_path.suffix == _SQL_SUFFIX
    )
    if not sql_files:
        return ()
    rows: list[tuple[str, list[str], list[str]]] = _native.inventory_sql_macros(
        [
            (sql_file.relative_path.stem, sql_file.relative_path.as_posix(), sql_file.contents)
            for sql_file in sql_files
        ]
    )
    return tuple(zip(sql_files, (tuple(row) for row in rows), strict=True))  # type: ignore[arg-type]


def _raise_sql_macro_call(*_arguments: object, sql_macro_name: str, **_keywords: object) -> str:
    name: str = sql_macro_name
    raise CompileInputError(
        f"{name}() is a SQL macro, called as a Python macro with @py.{name}()",
        code="P020",
        help=f"call it as @sql.{name}(...)",
    )


def _sql_macro_function(*, name: str, parameters: list[str]) -> Callable[..., object]:
    """A stand-in callable for a SQL macro whose signature names its parameters."""

    function: partial[str] = partial(_raise_sql_macro_call, sql_macro_name=name)
    function.__dict__["__signature__"] = inspect.Signature(
        [
            inspect.Parameter(parameter, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            for parameter in parameters
        ]
    )
    return function


def _load_python_macros(macro_files: tuple[DiscoveredMacroFile, ...]) -> dict[str, LoadedMacro]:
    """Load the Python macro modules' public functions into a collision-checked registry."""

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
    root, package_names, load_order = _native.macro_module_load_plan(
        [
            (
                name,
                str(analysis.file.file_path),
                analysis.file.contents,
                list(analysis.module_dependencies),
            )
            for name, analysis in analyses.items()
        ]
    )
    synthetic_names: list[str] = []
    previous_modules: dict[str, ModuleType] = {}
    modules: dict[str, ModuleType] = {}
    try:
        for package_name in package_names:
            package: ModuleType = ModuleType(package_name)
            package.__package__ = package_name
            package.__path__ = []  # type: ignore[attr-defined]
            previous: ModuleType | None = sys.modules.get(package_name)
            if previous is not None:
                previous_modules[package_name] = previous
            sys.modules[package_name] = package
            synthetic_names.append(package_name)

        name: str
        for name in load_order:
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


def inventory_project_macros(
    *, macro_files: tuple[DiscoveredMacroFile, ...]
) -> StaticMacroInventory:
    """Validate and inventory project macro exports without executing authored code."""

    python_files: tuple[DiscoveredMacroFile, ...] = tuple(
        macro_file for macro_file in macro_files if macro_file.relative_path.suffix != _SQL_SUFFIX
    )
    inventory: StaticMacroInventory
    inventory, _loads = _native_macro_inventory(
        macro_files=python_files,
        trees=tuple(_parse_macro_module(macro_file=macro_file) for macro_file in python_files),
    )
    exports: list[StaticMacroExport] = []
    faults: list[StaticMacroFault] = []
    for sql_file in macro_files:
        if sql_file.relative_path.suffix != _SQL_SUFFIX:
            continue
        try:
            exports.extend(
                _sql_macro_export(sql_file=parsed_file, row=row)
                for parsed_file, row in _sql_macro_rows((sql_file,))
            )
        except CompileInputError as error:
            faults.append(
                StaticMacroFault(relative_path=sql_file.relative_path, message=str(error))
            )
    return replace(
        inventory,
        exports=(*inventory.exports, *exports),
        faults=(*inventory.faults, *faults),
    )


def _sql_macro_export(
    *, sql_file: DiscoveredMacroFile, row: tuple[str, list[str], list[str]]
) -> StaticMacroExport:
    """The static export of one parsed SQL macro file."""

    name, parameters, calls = row
    dependencies: tuple[DeclarationIdentity, ...] = tuple(
        DeclarationIdentity(DeclarationKind.MACRO, called) for called in calls
    )
    return StaticMacroExport(
        name=name,
        relative_path=sql_file.relative_path,
        parameters=tuple(parameters),
        line=1,
        source_digest=hashlib.sha256(sql_file.contents.encode()).hexdigest(),
        dependencies=dependencies,
    )


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
