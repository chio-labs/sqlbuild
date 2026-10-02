"""Projection of discovered compiler inputs into canonical scope facts."""

from __future__ import annotations

import hashlib
import inspect
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from types import CodeType

from sqlbuild.compiler.compile.main._scope_relationship_grants import (
    build_scope_relationship_grants,
)
from sqlbuild.compiler.compile.main._static_macro_inventory import inventory_project_macros
from sqlbuild.compiler.compile.models import (
    LoadedMacro,
    ScopeRelationshipBuild,
    StaticMacroExport,
    StaticMacroInventory,
)
from sqlbuild.compiler.discovery.main._scope_snapshot import discover_scope_snapshot
from sqlbuild.compiler.discovery.models import (
    ConstantDeclaration,
    DiscoveredAuditFile,
    DiscoveredConstantFile,
    DiscoveredEnumFile,
    DiscoveredHookFunction,
    DiscoveredMacroFile,
    DiscoveredModelSchemaFile,
    DiscoveredProjectInputs,
    DiscoveredSqlHookFile,
    DiscoveryFileFault,
    EnumDeclaration,
    TolerantScopeDiscovery,
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
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
    UsageKind,
)
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax
from sqlbuild.sql_values.types import SqlValueKind

_ROOTS: dict[ResourceKind, str] = {
    ResourceKind.MODEL: "models",
    ResourceKind.TEST: "tests/unit",
    ResourceKind.SCENARIO: "tests/scenarios",
    ResourceKind.FUNCTION: "functions/sql",
    ResourceKind.SOURCE: "sources",
}
_SEED_ROOT: OwnershipRoot = OwnershipRoot("seeds", OwnershipRootKind.GLOBAL, ResourceKind.SEED)
_PYTHON_FUNCTION_ROOT: OwnershipRoot = OwnershipRoot(
    "functions/python", OwnershipRootKind.GLOBAL, ResourceKind.FUNCTION
)


@dataclass(frozen=True)
class _NamedPlacement:
    scope: ScopeKind
    ownership_root: OwnershipRoot
    owning_path: str | None

    @classmethod
    def of(
        cls,
        item: DiscoveredAuditFile
        | DiscoveredModelSchemaFile
        | DiscoveredSqlHookFile
        | DiscoveredHookFunction,
    ) -> _NamedPlacement:
        fallback: str = normalize_path(path=item.declaration_root or item.relative_path.parent)
        return cls(
            scope=item.scope_kind,
            ownership_root=_root(path=item.ownership_root, fallback=fallback),
            owning_path=(
                normalize_path(path=item.owning_path) if item.owning_path is not None else None
            ),
        )

    def record(self, *, kind: DeclarationKind, name: str, path: Path) -> DeclarationRecord:
        return DeclarationRecord(
            identity=DeclarationIdentity(kind, name),
            path=normalize_path(path=path),
            line=1,
            column=1,
            scope=self.scope,
            ownership_root=self.ownership_root,
            owning_path=self.owning_path,
        )


def build_index(
    *,
    discovered_inputs: DiscoveredProjectInputs,
    loaded_macros: Mapping[str, LoadedMacro] | None,
    static_macros: tuple[StaticMacroExport, ...] = (),
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
    for python_function_file in discovered_inputs.python_function_files:
        resources.append(
            ResourceRecord(
                identity=ResourceIdentity(
                    ResourceKind.FUNCTION, python_function_file.file_path.stem
                ),
                path=normalize_path(path=python_function_file.relative_path),
                ownership_root=_PYTHON_FUNCTION_ROOT,
            )
        )
    for seed_file in discovered_inputs.seed_files:
        resources.append(
            ResourceRecord(
                identity=ResourceIdentity(ResourceKind.SEED, seed_file.file_path.stem),
                path=normalize_path(path=seed_file.relative_path),
                ownership_root=_SEED_ROOT,
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
    declarations.extend(_named_declaration_records(discovered_inputs=discovered_inputs))
    if loaded_macros is not None:
        macro_files: dict[str, DiscoveredMacroFile] = {
            normalize_path(path=item.relative_path): item for item in discovered_inputs.macro_files
        }
        for loaded in loaded_macros.values():
            declarations.append(_macro_record(loaded=loaded, files=macro_files))
    else:
        macro_files = {
            normalize_path(path=item.relative_path): item for item in discovered_inputs.macro_files
        }
        declarations.extend(
            _static_macro_record(item=macro, files=macro_files) for macro in static_macros
        )

    diagnostics: tuple[ScopeDiagnostic, ...] = tuple(
        sorted(
            (*_resource_diagnostics(resources), *_declaration_diagnostics(declarations)),
            key=_diagnostic_key,
        )
    )
    usages: tuple[UsageRecord, ...] = _macro_dependency_usages(declarations=declarations)
    return ScopeIndex(
        ownership_roots=tuple(
            OwnershipRoot(path=path, resource_kind=kind)
            for kind, path in sorted(_ROOTS.items(), key=lambda item: item[1])
        ),
        resources=tuple(sorted(resources, key=_resource_key)),
        declarations=tuple(sorted(declarations, key=_declaration_key)),
        usages=usages,
        diagnostics=diagnostics,
        completeness=ScopeCompleteness(
            runtime_usage=False,
            relationships=False,
            placement=False,
            promotion_impact=False,
        ),
    )


def _macro_dependency_usages(*, declarations: list[DeclarationRecord]) -> tuple[UsageRecord, ...]:
    usages: list[UsageRecord] = []
    for record in declarations:
        if record.macro is None:
            continue
        for dependency in record.macro.dependencies:
            usages.append(
                UsageRecord(
                    consumer=record.identity,
                    declaration=dependency,
                    kind=UsageKind.DECLARATION_DEPENDENCY,
                )
            )
    return tuple(dict.fromkeys(usages))


def build_tolerant_scope_index(
    *, project_dir: Path, sql_lexical_syntax: SqlLexicalSyntax
) -> ScopeIndex:
    """Build a partial static index from published tolerant compiler facts."""

    snapshot: TolerantScopeDiscovery = discover_scope_snapshot(project_dir=project_dir)
    macro_inventory: StaticMacroInventory = inventory_project_macros(
        macro_files=snapshot.discovered_inputs.macro_files
    )
    index: ScopeIndex = build_index(
        discovered_inputs=snapshot.discovered_inputs,
        loaded_macros=None,
        static_macros=macro_inventory.exports,
    )
    relationships: ScopeRelationshipBuild = build_scope_relationship_grants(
        discovered_inputs=snapshot.discovered_inputs,
        index=index,
        sql_lexical_syntax=sql_lexical_syntax,
    )
    diagnostics: tuple[ScopeDiagnostic, ...] = _tolerant_diagnostics(
        snapshot=snapshot,
        macro_inventory=macro_inventory,
        relationships=relationships,
    )
    prospective: tuple[ResourceRecord, ...] = tuple(
        record
        for fault in (*snapshot.resource_faults, *snapshot.relationship_faults)
        if fault.path is not None
        if (record := _prospective_resource(path=fault.path)) is not None
    )
    return replace(
        index,
        grants=relationships.grants,
        resources=tuple(
            sorted(
                dict.fromkeys((*index.resources, *prospective)),
                key=_resource_key,
            )
        ),
        diagnostics=tuple(
            sorted(
                (*index.diagnostics, *diagnostics),
                key=_diagnostic_key,
            )
        ),
        completeness=ScopeCompleteness(
            discovery=False,
            static_visibility=not (
                snapshot.declaration_faults or snapshot.config_faults or macro_inventory.faults
            ),
            runtime_usage=False,
            relationships=not snapshot.relationship_faults and not relationships.faults,
            placement=False,
            promotion_impact=False,
        ),
    )


def _tolerant_diagnostics(
    *,
    snapshot: TolerantScopeDiscovery,
    macro_inventory: StaticMacroInventory,
    relationships: ScopeRelationshipBuild,
) -> tuple[ScopeDiagnostic, ...]:
    diagnostics: list[ScopeDiagnostic] = []
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.RESOURCE_PARSE_ERROR)
        for fault in snapshot.resource_faults
    )
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.DECLARATION_PARSE_ERROR)
        for fault in snapshot.declaration_faults
    )
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.RELATIONSHIP_PARSE_ERROR)
        for fault in snapshot.relationship_faults
    )
    diagnostics.extend(
        _discovery_diagnostic(fault=fault, code=ScopeDiagnosticCode.CONFIG_PARSE_ERROR)
        for fault in snapshot.config_faults
    )
    diagnostics.extend(
        ScopeDiagnostic(
            ScopeDiagnosticCode.MACRO_PARSE_ERROR,
            fault.message,
            path=fault.relative_path.as_posix(),
        )
        for fault in macro_inventory.faults
    )
    diagnostics.extend(
        ScopeDiagnostic(
            ScopeDiagnosticCode.RELATIONSHIP_PARSE_ERROR,
            fault.message,
            path=fault.relative_path.as_posix(),
        )
        for fault in relationships.faults
    )
    return tuple(diagnostics)


def _discovery_diagnostic(
    *, fault: DiscoveryFileFault, code: ScopeDiagnosticCode
) -> ScopeDiagnostic:
    return ScopeDiagnostic(
        code,
        fault.message,
        path=fault.path.as_posix() if fault.path is not None else None,
    )


def _prospective_resource(*, path: Path) -> ResourceRecord | None:
    relative: str = path.as_posix()
    for kind, root in _ROOTS.items():
        if relative.startswith(f"{root}/"):
            return ResourceRecord(
                ResourceIdentity(kind, path.stem),
                relative,
                OwnershipRoot(root, resource_kind=kind),
            )
    return None


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


def _named_declaration_records(
    *, discovered_inputs: DiscoveredProjectInputs
) -> list[DeclarationRecord]:
    records: list[DeclarationRecord] = []
    for audit_file in discovered_inputs.audit_files:
        placement: _NamedPlacement = _NamedPlacement.of(audit_file)
        if audit_file.declaration_kind is DeclarationKind.AUDIT:
            records.append(
                placement.record(
                    kind=DeclarationKind.AUDIT,
                    name=audit_file.relative_path.stem,
                    path=audit_file.relative_path,
                )
            )
            continue
        records.extend(
            placement.record(
                kind=DeclarationKind.SINGULAR_AUDIT,
                name=block.name or audit_file.relative_path.stem,
                path=audit_file.relative_path,
            )
            for block in audit_file.blocks
        )
    for schema_file in discovered_inputs.model_schema_files:
        placement = _NamedPlacement.of(schema_file)
        records.extend(
            placement.record(
                kind=DeclarationKind.SCHEMA, name=declaration.name, path=schema_file.relative_path
            )
            for declaration in schema_file.declarations
        )
    for hook_file in discovered_inputs.sql_hook_files:
        records.append(
            _NamedPlacement.of(hook_file).record(
                kind=DeclarationKind.SQL_HOOK, name=hook_file.name, path=hook_file.relative_path
            )
        )
    for hook_function in discovered_inputs.hook_functions:
        records.append(
            _NamedPlacement.of(hook_function).record(
                kind=DeclarationKind.PYTHON_HOOK,
                name=hook_function.name,
                path=hook_function.relative_path,
            )
        )
    return records


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
            members=tuple(EnumMemberMetadata(item.name) for item in declaration.members),
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
            dependencies=loaded.dependencies,
            source_digest=hashlib.sha256(loaded.raw_source.encode()).hexdigest(),
        ),
    )


def _static_macro_record(
    *, item: StaticMacroExport, files: dict[str, DiscoveredMacroFile]
) -> DeclarationRecord:
    path: str = normalize_path(path=item.relative_path)
    discovered: DiscoveredMacroFile | None = files.get(path)
    return DeclarationRecord(
        identity=DeclarationIdentity(DeclarationKind.MACRO, item.name),
        path=path,
        line=item.line,
        column=1,
        scope=discovered.scope_kind if discovered is not None else ScopeKind.GLOBAL,
        ownership_root=_root(
            path=discovered.ownership_root if discovered is not None else None,
            fallback="macros",
        ),
        owning_path=(
            normalize_path(path=discovered.owning_path)
            if discovered is not None and discovered.owning_path is not None
            else None
        ),
        macro=MacroMetadata(
            parameters=item.parameters,
            dependencies=item.dependencies,
            source_digest=item.source_digest,
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
