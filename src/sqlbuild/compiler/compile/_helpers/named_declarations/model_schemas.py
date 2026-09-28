"""Scope facts for reusable model schemas: parent schemas and enum column types."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.named_declarations.core import (
    named_declaration_record,
    named_declaration_usages,
)
from sqlbuild.compiler.compile.models import CompilerDiagnostic, DeclarationScopeResolver
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import (
    DiscoveredModelSchemaFile,
    EnumDeclaration,
    ModelSchemaDeclaration,
)
from sqlbuild.compiler.scopes.main._declaration_visibility import declaration_visibility
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeDiagnosticCode


def model_schema_scope_usages(
    *,
    schema_files: tuple[DiscoveredModelSchemaFile, ...],
    resolver: DeclarationScopeResolver | None,
) -> tuple[UsageRecord, ...]:
    """Require parent schemas and enum column types to be visible from each schema's folder."""

    if resolver is None:
        return ()
    usages: list[UsageRecord] = []
    for schema_file in schema_files:
        for declaration in schema_file.declarations:
            record: DeclarationRecord | None = named_declaration_record(
                resolver=resolver, kind=DeclarationKind.SCHEMA, name=declaration.name
            )
            if record is None:
                continue
            if declaration.extends is not None:
                usages.extend(
                    named_declaration_usages(
                        resolver=resolver,
                        kind=DeclarationKind.SCHEMA,
                        name=declaration.extends,
                        consumer=record.identity,
                        consumer_path=record,
                    )
                )
            usages.extend(
                UsageRecord(consumer=record.identity, declaration=enum_record.identity)
                for enum_record in _enum_type_records(
                    declaration=declaration, record=record, resolver=resolver
                )
            )
    return tuple(dict.fromkeys(usages))


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


def _enum_type_records(
    *,
    declaration: ModelSchemaDeclaration,
    record: DeclarationRecord,
    resolver: DeclarationScopeResolver,
) -> tuple[DeclarationRecord, ...]:
    records: list[DeclarationRecord] = []
    for column in declaration.columns:
        if column.type is None:
            continue
        enum_record: DeclarationRecord | None = named_declaration_record(
            resolver=resolver, kind=DeclarationKind.ENUM, name=column.type
        )
        if enum_record is None:
            continue
        if declaration_visibility(declaration=enum_record, consumer=record) is None:
            owner: str = enum_record.owning_path or enum_record.ownership_root.path
            report_compile_diagnostic(
                key=(
                    ScopeDiagnosticCode.INACCESSIBLE_DECLARATION.value,
                    record.path,
                    declaration.name,
                    column.name,
                ),
                diagnostic=CompilerDiagnostic(
                    phase=DiagnosticPhase.COMPILE,
                    severity=DiagnosticSeverity.ERROR,
                    code=ScopeDiagnosticCode.INACCESSIBLE_DECLARATION.value,
                    message=(
                        f"Schema '{declaration.name}' in {record.path} column '{column.name}' "
                        f"uses enum '{column.type}', which is not visible from the schema's "
                        f"location. The enum is defined at {enum_record.path} with "
                        f"{enum_record.scope.value} scope owned by '{owner}'"
                    ),
                    path=Path(record.path),
                    help=(
                        "move the enum to a role visible from the schema's owning folder, or "
                        "move the schema next to the enum"
                    ),
                ),
            )
        records.append(enum_record)
    return tuple(records)
