"""Persistent canonical scope-index caching over the native fingerprint and codec."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import sqlbuild._native as _native
from sqlbuild.compiler.discovery.constants import (
    CANONICAL_AUTHORED_ROOTS,
    LOCAL_CONFIG_FILENAME,
    PROJECT_CONFIG_FILENAME,
)
from sqlbuild.compiler.frontier.main.compiler_cache_directory import compiler_cache_directory
from sqlbuild.compiler.scopes._helpers.placement import qualified_row, root_row
from sqlbuild.compiler.scopes.constants import (
    GLOBAL_DECLARATION_DIRECTORIES,
    GLOBAL_NAMED_DECLARATION_DIRECTORIES,
    SCOPE_CACHE_DIRECTORY_NAME,
    SCOPE_CACHE_FILENAME,
)
from sqlbuild.compiler.scopes.models import (
    ConstantMetadata,
    DeclarationIdentity,
    DeclarationRecord,
    EnumMemberMetadata,
    EnumMetadata,
    GrantRecord,
    InaccessibleRecord,
    MacroMetadata,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeDiagnostic,
    ScopeIndex,
    UsageRecord,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    DiagnosticSeverity,
    GrantKind,
    InaccessibleReason,
    NativeQualifiedRow,
    OwnershipRootKind,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
    UsageKind,
    VisibilityReason,
)

_CONFIG_FILES: tuple[str, ...] = (
    PROJECT_CONFIG_FILENAME,
    LOCAL_CONFIG_FILENAME,
    ".sqlbuildignore",
    ".gitignore",
)
_SOURCE_ROOTS: tuple[str, ...] = (
    *(Path(*parts).as_posix() for parts in CANONICAL_AUTHORED_ROOTS),
    *GLOBAL_DECLARATION_DIRECTORIES,
    *GLOBAL_NAMED_DECLARATION_DIRECTORIES,
    "python",
    "seeds",
)
_RESOURCE_KINDS: frozenset[str] = frozenset(kind.value for kind in ResourceKind)


def scope_index_fingerprint(*, project_dir: Path) -> str | None:
    """Hash canonical scope-relevant authored inputs, or None when they cannot be read."""

    return _native.scope_index_fingerprint(
        project_dir,
        (
            list(_CONFIG_FILES),
            list(_SOURCE_ROOTS),
            sorted(GLOBAL_DECLARATION_DIRECTORIES),
            sorted(GLOBAL_NAMED_DECLARATION_DIRECTORIES),
            _sqlbuild_version(),
        ),
    )


def read_cached_scope_index(*, project_dir: Path, fingerprint: str) -> ScopeIndex | None:
    """Read a verified index; every storage or validation fault is a cache miss."""

    rows: Any = _native.read_scope_index_cache(
        compiler_cache_directory(project_dir) / SCOPE_CACHE_DIRECTORY_NAME / SCOPE_CACHE_FILENAME,
        fingerprint,
    )
    if rows is None:
        return None
    try:
        return _index(rows)
    except ValueError:
        return None


def write_cached_scope_index(*, project_dir: Path, fingerprint: str, index: ScopeIndex) -> None:
    """Atomically write one complete canonical scope index, ignoring I/O faults."""

    if not index.completeness.complete:
        return
    _ = _native.write_scope_index_cache(
        (compiler_cache_directory(project_dir) / SCOPE_CACHE_DIRECTORY_NAME, SCOPE_CACHE_FILENAME),
        fingerprint,
        _rows(index),
    )


def _rows(index: ScopeIndex) -> Any:
    completeness: ScopeCompleteness = index.completeness
    return (
        [root_row(root=root) for root in index.ownership_roots],
        [
            (_resource_row(record.identity), record.path, root_row(root=record.ownership_root))
            for record in index.resources
        ],
        [_declaration_row(record) for record in index.declarations],
        [
            (
                qualified_row(identity=item.consumer),
                qualified_row(identity=item.declaration),
                item.kind.value,
                _optional_row(item.through),
                item.enum_member,
            )
            for item in index.usages
        ],
        [
            (
                _resource_row(item.resource),
                qualified_row(identity=item.declaration),
                qualified_row(identity=item.through),
                item.kind.value,
            )
            for item in index.grants
        ],
        [
            (
                _resource_row(item.resource),
                qualified_row(identity=item.declaration),
                item.reason.value,
                _optional_row(item.through),
            )
            for item in index.visibility
        ],
        [
            (
                _resource_row(item.resource),
                qualified_row(identity=item.declaration),
                item.reason.value,
            )
            for item in index.inaccessible
        ],
        [
            (
                item.code.value,
                item.message,
                item.severity.value,
                item.path,
                item.line,
                item.column,
                _optional_row(item.declaration),
                None if item.resource is None else _resource_row(item.resource),
            )
            for item in index.diagnostics
        ],
        (
            completeness.discovery,
            completeness.static_visibility,
            completeness.runtime_usage,
            completeness.relationships,
            completeness.placement,
            completeness.promotion_impact,
        ),
    )


def _declaration_row(record: DeclarationRecord) -> Any:
    return (
        (
            qualified_row(identity=record.identity),
            record.path,
            record.line,
            record.column,
            record.scope.value,
            root_row(root=record.ownership_root),
            record.owning_path,
        ),
        None
        if record.macro is None
        else (
            list(record.macro.parameters),
            [qualified_row(identity=item) for item in record.macro.dependencies],
            record.macro.source_digest,
        ),
        None
        if record.enum is None
        else ([member.name for member in record.enum.members], record.enum.scalar_type),
        None
        if record.constant is None
        else (
            record.constant.logical_type,
            record.constant.collection_kind,
            record.constant.item_count,
            record.constant.nullable,
            record.constant.render_as,
        ),
    )


def _resource_row(identity: ResourceIdentity) -> tuple[str, str]:
    return identity.kind.value, identity.name


def _optional_row(identity: ResourceIdentity | DeclarationIdentity | None) -> object:
    return None if identity is None else qualified_row(identity=identity)


def _index(rows: Any) -> ScopeIndex:
    roots, resources, declarations, usages, grants, visibility, inaccessible, diagnostics, done = (
        rows
    )
    return ScopeIndex(
        ownership_roots=tuple(map(_root, roots)),
        resources=tuple(
            ResourceRecord(_resource(identity), path, _root(root))
            for identity, path, root in resources
        ),
        declarations=tuple(map(_declaration, declarations)),
        usages=tuple(
            UsageRecord(
                _identity(consumer),
                _declaration_identity(declaration),
                UsageKind(kind),
                None if through is None else _identity(through),
                enum_member,
            )
            for consumer, declaration, kind, through, enum_member in usages
        ),
        grants=tuple(
            GrantRecord(
                _resource(resource),
                _declaration_identity(declaration),
                _identity(through),
                GrantKind(kind),
            )
            for resource, declaration, through, kind in grants
        ),
        visibility=tuple(
            VisibilityRecord(
                _resource(resource),
                _declaration_identity(declaration),
                VisibilityReason(reason),
                None if through is None else _identity(through),
            )
            for resource, declaration, reason, through in visibility
        ),
        inaccessible=tuple(
            InaccessibleRecord(
                _resource(resource), _declaration_identity(declaration), InaccessibleReason(reason)
            )
            for resource, declaration, reason in inaccessible
        ),
        diagnostics=tuple(map(_diagnostic, diagnostics)),
        completeness=ScopeCompleteness(*done),
    )


def _declaration(row: Any) -> DeclarationRecord:
    (identity, path, line, column, scope, root, owning_path), macro, enum, constant = row
    return DeclarationRecord(
        identity=_declaration_identity(identity),
        path=path,
        line=line,
        column=column,
        scope=ScopeKind(scope),
        ownership_root=_root(root),
        owning_path=owning_path,
        macro=None
        if macro is None
        else MacroMetadata(tuple(macro[0]), tuple(map(_declaration_identity, macro[1])), macro[2]),
        enum=None
        if enum is None
        else EnumMetadata(tuple(map(EnumMemberMetadata, enum[0])), enum[1]),
        constant=None if constant is None else ConstantMetadata(*constant),
    )


def _diagnostic(row: Any) -> ScopeDiagnostic:
    code, message, severity, path, line, column, declaration, resource = row
    return ScopeDiagnostic(
        ScopeDiagnosticCode(code),
        message,
        DiagnosticSeverity(severity),
        path,
        line,
        column,
        None if declaration is None else _declaration_identity(declaration),
        None if resource is None else _resource(resource),
    )


def _root(row: tuple[str, str, str | None]) -> OwnershipRoot:
    path, kind, resource_kind = row
    return OwnershipRoot(
        path,
        OwnershipRootKind(kind),
        None if resource_kind is None else ResourceKind(resource_kind),
    )


def _resource(row: tuple[str, str]) -> ResourceIdentity:
    return ResourceIdentity(ResourceKind(row[0]), row[1])


def _declaration_identity(row: NativeQualifiedRow) -> DeclarationIdentity:
    kind, name, owner = row
    return DeclarationIdentity(
        DeclarationKind(kind), name, None if owner is None else _resource(owner)
    )


def _identity(row: NativeQualifiedRow) -> ResourceIdentity | DeclarationIdentity:
    if row[2] is None and row[0] in _RESOURCE_KINDS:
        return _resource((row[0], row[1]))
    return _declaration_identity(row)


def _sqlbuild_version() -> str:
    try:
        return version("sqlbuild")
    except PackageNotFoundError:
        return "0+unknown"
