"""Scope facts for reusable model schemas: parent schemas and enum column types."""

from __future__ import annotations

from itertools import chain
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile.models import CompilerDiagnostic, DeclarationScopeResolver
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import (
    DiscoveredModelSchemaFile,
    EnumDeclaration,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeDiagnosticCode

_SCHEMA_USAGE_KINDS: frozenset[DeclarationKind] = frozenset(
    {DeclarationKind.SCHEMA, DeclarationKind.ENUM}
)


def model_schema_scope_usages(
    *,
    schema_files: tuple[DiscoveredModelSchemaFile, ...],
    resolver: DeclarationScopeResolver | None,
) -> tuple[UsageRecord, ...]:
    """Require parent schemas and enum column types to be visible from each schema's folder."""

    if resolver is None:
        return ()
    records: list[DeclarationRecord] = [
        found[0]
        for identity, found in resolver.lookup.declarations.items()
        if found and identity.owner is None and identity.kind in _SCHEMA_USAGE_KINDS
    ]
    usages: list[tuple[int, int]]
    diagnostics: list[tuple[list[str], str, str, str]]
    error: str | None
    usages, diagnostics, error = _native.scope_schema_usages(
        list(map(_schema_row, chain.from_iterable(item.declarations for item in schema_files))),
        list(map(_record_row, records)),
    )
    if error is not None:
        raise InvalidScopePathError(error)
    for key, message, path, help_text in diagnostics:
        report_compile_diagnostic(
            key=tuple(key),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=ScopeDiagnosticCode.INACCESSIBLE_DECLARATION.value,
                message=message,
                path=Path(path),
                help=help_text,
            ),
        )
    return tuple(
        UsageRecord(consumer=records[consumer].identity, declaration=records[used].identity)
        for consumer, used in usages
    )


def _schema_row(
    declaration: ModelSchemaDeclaration,
) -> tuple[str, str | None, list[tuple[str, str | None]]]:
    return (
        declaration.name,
        declaration.extends,
        [(column.name, column.type) for column in declaration.columns],
    )


def _record_row(
    record: DeclarationRecord,
) -> tuple[tuple[str, str], tuple[str, str, tuple[str, str] | None, str | None, str]]:
    owner: ResourceIdentity | None = record.identity.owner
    return (
        (record.identity.kind.value, record.identity.name),
        (
            record.path,
            record.scope.value,
            None if owner is None else (owner.kind.value, owner.name),
            record.owning_path,
            record.ownership_root.path,
        ),
    )


def model_schema_enum_declarations(
    *, schema: ModelSchemaDeclaration, resolver: DeclarationScopeResolver | None
) -> dict[str, EnumDeclaration]:
    """Return enum column types resolved from the schema's own location."""

    if resolver is None:
        return {}
    enums: dict[str, EnumDeclaration] = {}
    for column in schema.columns:
        if column.type is None:
            continue
        value: object = resolver.projection.declarations.get(
            DeclarationIdentity(DeclarationKind.ENUM, column.type)
        )
        if isinstance(value, EnumDeclaration):
            enums[column.type] = value
    return enums
