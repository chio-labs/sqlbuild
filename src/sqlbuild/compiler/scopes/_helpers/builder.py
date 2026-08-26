"""Projection of discovered compiler inputs into canonical scope facts."""

from __future__ import annotations

import hashlib
import inspect
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from types import CodeType

from sqlbuild.compiler.compile.models import LoadedMacro
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredMacroFile,
    DiscoveredProjectInputs,
    EnumDeclaration,
)
from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes.constants import GLOBAL_DECLARATION_DIRECTORIES
from sqlbuild.compiler.scopes.models import (
    ConstantMetadata,
    DeclarationIdentity,
    DeclarationRecord,
    EnumMemberMetadata,
    EnumMetadata,
    MacroMetadata,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeIndex,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
)
from sqlbuild.sql_values.types import SqlValueKind

_ROOTS: dict[ResourceKind, str] = {
    ResourceKind.MODEL: "models",
    ResourceKind.TEST: "tests/unit",
    ResourceKind.SCENARIO: "tests/scenarios",
    ResourceKind.HOOK: "hooks/sql",
    ResourceKind.FUNCTION: "functions/sql",
    ResourceKind.AUDIT: "audits",
    ResourceKind.SOURCE: "sources",
}


def build_index(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: Mapping[str, LoadedMacro] | None,
) -> ScopeIndex:
    resources: list[ResourceRecord] = []
    declarations: list[DeclarationRecord] = []

    for model_file in discovered_inputs.model_files:
        model_name: str = _name_or_stem(
            value=model_file.header_values.get("name"), path=model_file.relative_path
        )
        resources.append(
            _resource_record(
                kind=ResourceKind.MODEL, name=model_name, path=model_file.relative_path
            )
        )
        owner: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, model_name)
        declarations.extend(
            _private_declarations(
                enums=model_file.enum_declarations,
                constants=model_file.constant_declarations,
                owner=owner,
                path=model_file.relative_path,
            )
        )
    for test_file in discovered_inputs.test_files:
        for block in test_file.blocks:
            resources.append(
                _resource_record(
                    kind=ResourceKind.TEST,
                    name=block.name or test_file.relative_path.stem,
                    path=test_file.relative_path,
                )
            )
    for scenario_file in discovered_inputs.scenario_files:
        resources.append(
            _resource_record(
                kind=ResourceKind.SCENARIO,
                name=scenario_file.name,
                path=scenario_file.relative_path,
            )
        )
    for hook_file in discovered_inputs.sql_hook_files:
        resources.append(
            _resource_record(
                kind=ResourceKind.HOOK, name=hook_file.name, path=hook_file.relative_path
            )
        )
    for function_file in discovered_inputs.sql_function_files:
        resources.append(
            _resource_record(
                kind=ResourceKind.FUNCTION,
                name=_name_or_stem(
                    value=function_file.header_values.get("name"),
                    path=function_file.relative_path,
                ),
                path=function_file.relative_path,
            )
        )
    for audit_file in discovered_inputs.audit_files:
        for block in audit_file.blocks:
            resources.append(
                _resource_record(
                    kind=ResourceKind.AUDIT,
                    name=block.name or audit_file.relative_path.stem,
                    path=audit_file.relative_path,
                )
            )
    for source_file in discovered_inputs.source_files:
        for source in source_file.source_entries:
            resources.append(
                _resource_record(
                    kind=ResourceKind.SOURCE,
                    name=source.name,
                    path=source_file.relative_path,
                )
            )

    for enum_file in discovered_inputs.enum_files:
        declarations.extend(_enum_file_records(enum_file))
    for constant_file in discovered_inputs.constant_files:
        declarations.extend(_constant_file_records(constant_file))
    if loaded_macros is not None:
        macro_files: dict[str, DiscoveredMacroFile] = {
            normalize_path(path=item.relative_path): item for item in discovered_inputs.macro_files
        }
        for loaded in loaded_macros.values():
            declarations.append(_macro_record(loaded=loaded, files=macro_files))

    diagnostics: tuple[ScopeDiagnostic, ...] = tuple(
        sorted(
            (*_resource_diagnostics(resources), *_declaration_diagnostics(declarations)),
            key=_diagnostic_key,
        )
    )
    return ScopeIndex(
        resources=tuple(sorted(resources, key=_resource_key)),
        declarations=tuple(sorted(declarations, key=_declaration_key)),
        diagnostics=diagnostics,
        completeness=ScopeCompleteness(
            runtime_usage=False,
            relationships=False,
            placement=False,
            promotion_impact=False,
        ),
    )


def _resource_record(*, kind: ResourceKind, name: str, path: Path) -> ResourceRecord:
    root: str = _ROOTS[kind]
    return ResourceRecord(
        identity=ResourceIdentity(kind=kind, name=name),
        path=normalize_path(path=path),
        ownership_root=OwnershipRoot(path=root, resource_kind=kind),
    )


def _name_or_stem(*, value: object, path: Path) -> str:
    return value if isinstance(value, str) and value else path.stem


def _root(*, path: Path | None, fallback: str, kind: ResourceKind | None = None) -> OwnershipRoot:
    if path is None:
        return OwnershipRoot(fallback, OwnershipRootKind.GLOBAL)
    normalized: str = normalize_path(path=path)
    is_global: bool = normalized in GLOBAL_DECLARATION_DIRECTORIES
    resource_kind: ResourceKind | None = next(
        (item_kind for item_kind, item_path in _ROOTS.items() if item_path == normalized),
        None,
    )
    return OwnershipRoot(
        normalized,
        OwnershipRootKind.GLOBAL if is_global else OwnershipRootKind.RESOURCE,
        resource_kind=kind or resource_kind,
    )


def _enum_file_records(file: DiscoveredEnumFile) -> list[DeclarationRecord]:
    return [
        _enum_record(
            declaration=item,
            scope=file.scope_kind,
            ownership_root=_root(path=file.ownership_root, fallback="enums"),
            owning_path=file.owning_path,
            path=file.relative_path,
        )
        for item in file.declarations
    ]


def _constant_file_records(file: DiscoveredConstantFile) -> list[DeclarationRecord]:
    return [
        _constant_record(
            declaration=item,
            scope=file.scope_kind,
            ownership_root=_root(path=file.ownership_root, fallback="constants"),
            owning_path=file.owning_path,
            path=file.relative_path,
        )
        for item in file.declarations
    ]


def _private_declarations(
    *,
    enums: tuple[EnumDeclaration, ...],
    constants: tuple[ConstantDeclaration, ...],
    owner: ResourceIdentity,
    path: Path,
) -> list[DeclarationRecord]:
    root: OwnershipRoot = OwnershipRoot("models", resource_kind=ResourceKind.MODEL)
    return [
        _enum_record(
            declaration=item,
            scope=ScopeKind.PRIVATE,
            ownership_root=root,
            owning_path=path.parent,
            path=path,
            owner=owner,
        )
        for item in enums
    ] + [
        _constant_record(
            declaration=item,
            scope=ScopeKind.PRIVATE,
            ownership_root=root,
            owning_path=path.parent,
            path=path,
            owner=owner,
        )
        for item in constants
    ]


def _enum_record(
    *,
    declaration: EnumDeclaration,
    scope: ScopeKind,
    ownership_root: OwnershipRoot,
    owning_path: Path | None,
    path: Path,
    owner: ResourceIdentity | None = None,
) -> DeclarationRecord:
    return DeclarationRecord(
        identity=DeclarationIdentity(DeclarationKind.ENUM, declaration.name, owner),
        path=normalize_path(path=path),
        line=1,
        column=1,
        scope=scope,
        ownership_root=ownership_root,
        owning_path=normalize_path(path=owning_path) if owning_path is not None else None,
        enum=EnumMetadata(
            members=tuple(
                EnumMemberMetadata(item.name, item.value) for item in declaration.members
            ),
            scalar_type=declaration.scalar_type,
        ),
    )


def _constant_record(
    *,
    declaration: ConstantDeclaration,
    scope: ScopeKind,
    ownership_root: OwnershipRoot,
    owning_path: Path | None,
    path: Path,
    owner: ResourceIdentity | None = None,
) -> DeclarationRecord:
    collection_kinds: frozenset[SqlValueKind] = frozenset(
        {SqlValueKind.LIST, SqlValueKind.SET, SqlValueKind.OBJECT}
    )
    is_collection: bool = declaration.value.kind in collection_kinds
    payload: object = declaration.value.value
    item_count: int | None = len(payload) if is_collection and isinstance(payload, tuple) else None
    return DeclarationRecord(
        identity=DeclarationIdentity(DeclarationKind.CONSTANT, declaration.name, owner),
        path=normalize_path(path=path),
        line=1,
        column=1,
        scope=scope,
        ownership_root=ownership_root,
        owning_path=normalize_path(path=owning_path) if owning_path is not None else None,
        constant=ConstantMetadata(
            logical_type=declaration.logical_type.display_name,
            collection_kind=declaration.value.kind.value if is_collection else None,
            item_count=item_count,
            nullable=declaration.value.kind is SqlValueKind.NULL,
            render_as=declaration.render_as.value if declaration.render_as is not None else None,
        ),
    )


def _macro_record(
    *, loaded: LoadedMacro, files: dict[str, DiscoveredMacroFile]
) -> DeclarationRecord:
    path: str = normalize_path(path=loaded.relative_path)
    discovered: DiscoveredMacroFile | None = files.get(path)
    scope: ScopeKind = discovered.scope_kind if discovered is not None else ScopeKind.GLOBAL
    ownership_root: OwnershipRoot = _root(
        path=discovered.ownership_root if discovered is not None else None,
        fallback="macros",
    )
    owning_path: str | None = (
        normalize_path(path=discovered.owning_path)
        if discovered is not None and discovered.owning_path is not None
        else None
    )
    code: object = getattr(loaded.function, "__code__", None)
    line: int = code.co_firstlineno if isinstance(code, CodeType) else 1
    return DeclarationRecord(
        identity=DeclarationIdentity(DeclarationKind.MACRO, loaded.name),
        path=path,
        line=line,
        column=1,
        scope=scope,
        ownership_root=ownership_root,
        owning_path=owning_path,
        macro=MacroMetadata(
            parameters=tuple(inspect.signature(loaded.function).parameters),
            source_digest=hashlib.sha256(loaded.raw_source.encode()).hexdigest(),
        ),
    )


def _declaration_diagnostics(records: list[DeclarationRecord]) -> tuple[ScopeDiagnostic, ...]:
    diagnostics: list[ScopeDiagnostic] = []
    public: dict[tuple[DeclarationKind, str], list[DeclarationRecord]] = defaultdict(list)
    private: dict[DeclarationIdentity, list[DeclarationRecord]] = defaultdict(list)
    for record in records:
        name: str = record.identity.name
        if name.startswith("__"):
            diagnostics.append(
                _diagnostic(
                    record=record,
                    code=ScopeDiagnosticCode.RESERVED_DECLARATION_NAME,
                    message=f"Declaration name '{name}' uses reserved '__' prefix",
                )
            )
        elif record.scope is ScopeKind.PRIVATE and (
            not name.startswith("_") or name[1:].startswith("_")
        ):
            diagnostics.append(
                _diagnostic(
                    record=record,
                    code=ScopeDiagnosticCode.INVALID_DECLARATION_NAME,
                    message=(
                        f"Private declaration name '{name}' must have exactly one leading "
                        "underscore"
                    ),
                )
            )
        elif record.scope is not ScopeKind.PRIVATE and name.startswith("_"):
            diagnostics.append(
                _diagnostic(
                    record=record,
                    code=ScopeDiagnosticCode.INVALID_DECLARATION_NAME,
                    message=f"Public declaration name '{name}' must not start with underscore",
                )
            )
        if record.identity.owner is None:
            public[(record.identity.kind, name)].append(record)
        else:
            private[record.identity].append(record)
    for duplicates in (*public.values(), *private.values()):
        if len(duplicates) <= 1:
            continue
        locations: str = ", ".join(
            f"{item.path}:{item.line}:{item.column}"
            for item in sorted(duplicates, key=_declaration_key)
        )
        for record in duplicates:
            identity: str = format_identity(identity=record.identity)
            diagnostics.append(
                _diagnostic(
                    record=record,
                    code=ScopeDiagnosticCode.DUPLICATE_DECLARATION,
                    message=f"Duplicate declaration '{identity}' at {locations}",
                )
            )
    return tuple(sorted(diagnostics, key=_diagnostic_key))


def _resource_diagnostics(records: list[ResourceRecord]) -> tuple[ScopeDiagnostic, ...]:
    grouped: dict[ResourceIdentity, list[ResourceRecord]] = defaultdict(list)
    diagnostics: list[ScopeDiagnostic] = []
    for record in records:
        grouped[record.identity].append(record)
    for identity, duplicates in grouped.items():
        if len(duplicates) <= 1:
            continue
        locations: str = ", ".join(item.path for item in sorted(duplicates, key=_resource_key))
        identity_text: str = format_identity(identity=identity)
        for record in duplicates:
            diagnostics.append(
                ScopeDiagnostic(
                    ScopeDiagnosticCode.DUPLICATE_RESOURCE,
                    f"Duplicate resource '{identity_text}' at {locations}",
                    path=record.path,
                    line=1,
                    column=1,
                    resource=record.identity,
                )
            )
    return tuple(sorted(diagnostics, key=_diagnostic_key))


def _diagnostic(
    *, record: DeclarationRecord, code: ScopeDiagnosticCode, message: str
) -> ScopeDiagnostic:
    return ScopeDiagnostic(
        code,
        message,
        path=record.path,
        line=record.line,
        column=record.column,
        declaration=record.identity,
    )


def _resource_key(record: ResourceRecord) -> tuple[str, str]:
    return (record.path, format_identity(identity=record.identity))


def _declaration_key(record: DeclarationRecord) -> tuple[str, str, int, int]:
    return (format_identity(identity=record.identity), record.path, record.line, record.column)


def _diagnostic_key(item: ScopeDiagnostic) -> tuple[str, int, int, str, str]:
    return (item.path or "", item.line or 0, item.column or 0, item.code.value, item.message)
