"""The Python classes and project inputs the native model loop builds models with."""

from collections.abc import Callable
from pathlib import Path

from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    DeclarationScopeResolver,
    ModelInputBuildContext,
)
from sqlbuild.compiler.discovery.models import (
    DiscoveredAuditFactory,
    EnumDeclaration,
    SqlHookEntry,
)
from sqlbuild.compiler.model_config.main._native_config_error import native_config_error
from sqlbuild.compiler.planner.types import ContractPolicy
from sqlbuild.compiler.references.types import ExternalSqlReferenceResolver, SqlReferenceKind
from sqlbuild.compiler.scopes.models import DeclarationRecord, UsageRecord
from sqlbuild.compiler.scopes.types import DeclarationKind, UsageKind


def model_loop_classes(
    *,
    audit_factories: tuple[DiscoveredAuditFactory, ...],
    context: ModelInputBuildContext,
    report_diagnostic: Callable[..., None],
    external_resolver: ExternalSqlReferenceResolver | None,
) -> dict[str, object]:
    """Return the classes, error factories and project declarations the model loop reads."""

    resolver: DeclarationScopeResolver | None = context.declaration_resolver
    return {
        "usage_record": UsageRecord,
        "compile_error": CompileInputError,
        "sql_hook_entry": SqlHookEntry,
        "config_error": native_config_error,
        "audit_factories": {factory.name: factory for factory in audit_factories},
        "generated_usage": UsageKind.GENERATED,
        "contract_enforced": ContractPolicy.ENFORCED,
        "model_schemas": context.public_model_schemas,
        "schema_records": _schema_records(resolver),
        "schema_enums": _schema_enums(resolver),
        "compiler_diagnostic": CompilerDiagnostic,
        "report_diagnostic": report_diagnostic,
        "path_class": Path,
        "external_resolver": external_resolver,
        "reference_kind": SqlReferenceKind,
    }


def _schema_records(resolver: DeclarationScopeResolver | None) -> dict[str, DeclarationRecord]:
    """Each project-owned schema's first declaration record, as `named_declaration_record` reads."""

    if resolver is None:
        return {}
    records: dict[str, DeclarationRecord] = {}
    for identity, declarations in resolver.lookup.declarations.items():
        if identity.kind is DeclarationKind.SCHEMA and identity.owner is None and declarations:
            records[identity.name] = declarations[0]
    return records


def _schema_enums(resolver: DeclarationScopeResolver | None) -> dict[str, EnumDeclaration]:
    """Project-owned enums by name, as `model_schema_enum_declarations` resolves column types."""

    if resolver is None:
        return {}
    enums: dict[str, EnumDeclaration] = {}
    for identity, value in resolver.projection.declarations.items():
        if (
            identity.kind is DeclarationKind.ENUM
            and identity.owner is None
            and isinstance(value, EnumDeclaration)
        ):
            enums[identity.name] = value
    return enums
