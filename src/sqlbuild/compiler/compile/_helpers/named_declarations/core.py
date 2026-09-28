"""Visibility and usage facts for audits, reusable schemas, and named hooks used by name."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from sqlbuild.compiler.compile._helpers.diagnostics.collector import report_compile_diagnostic
from sqlbuild.compiler.compile._helpers.diagnostics.scope import compiled_resource_type
from sqlbuild.compiler.compile._helpers.render.declarations import resolve_declaration_expansion
from sqlbuild.compiler.compile.models import (
    CompilerDiagnostic,
    DeclarationExpansionContext,
    DeclarationScopeResolver,
)
from sqlbuild.compiler.compile.types import DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.scopes.constants import DECLARATION_ROLE_PARTS
from sqlbuild.compiler.scopes.main._declaration_lexical_path import declaration_lexical_path
from sqlbuild.compiler.scopes.main._declaration_visibility import declaration_visibility
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import DeclarationKind, ScopeDiagnosticCode

_KIND_LABELS: dict[DeclarationKind, str] = {
    DeclarationKind.AUDIT: "Generic audit",
    DeclarationKind.SCHEMA: "Schema",
    DeclarationKind.SQL_HOOK: "SQL hook",
    DeclarationKind.PYTHON_HOOK: "Python hook",
}


def named_declaration_record(
    *, resolver: DeclarationScopeResolver | None, kind: DeclarationKind, name: str
) -> DeclarationRecord | None:
    """Return the indexed project declaration, or None for built-ins and unindexed inputs."""

    if resolver is None:
        return None
    records: tuple[DeclarationRecord, ...] = resolver.lookup.declarations.get(
        DeclarationIdentity(kind, name), ()
    )
    return records[0] if records else None


def named_declaration_usages(
    *,
    resolver: DeclarationScopeResolver | None,
    kind: DeclarationKind,
    name: str,
    consumer: ResourceIdentity | DeclarationIdentity,
    consumer_path: Path | DeclarationRecord,
) -> tuple[UsageRecord, ...]:
    """Require a declaration to be visible from its consumer and return the usage fact."""

    record: DeclarationRecord | None = named_declaration_record(
        resolver=resolver, kind=kind, name=name
    )
    if record is None:
        return ()
    if (
        isinstance(consumer_path, Path)
        and consumer_path.is_absolute()
        and resolver is not None
        and resolver.project_dir is not None
        and consumer_path.is_relative_to(resolver.project_dir)
    ):
        consumer_path = consumer_path.relative_to(resolver.project_dir)
    lexical_consumer: str | DeclarationRecord = (
        consumer_path if isinstance(consumer_path, DeclarationRecord) else consumer_path.as_posix()
    )
    if declaration_visibility(declaration=record, consumer=lexical_consumer) is None:
        consumer_label: str = (
            consumer_path.path
            if isinstance(consumer_path, DeclarationRecord)
            else consumer_path.as_posix()
        )
        consumer_folder: str = (
            declaration_lexical_path(record=consumer_path).rsplit("/", maxsplit=1)[0]
            if isinstance(consumer_path, DeclarationRecord)
            else consumer_path.parent.as_posix()
        )
        owner: str = record.owning_path or record.ownership_root.path
        role: str = "/".join(DECLARATION_ROLE_PARTS[kind])
        resource: ResourceIdentity | None = (
            consumer if isinstance(consumer, ResourceIdentity) else None
        )
        report_compile_diagnostic(
            key=(
                ScopeDiagnosticCode.INACCESSIBLE_DECLARATION.value,
                consumer_label,
                kind.value,
                name,
            ),
            diagnostic=CompilerDiagnostic(
                phase=DiagnosticPhase.COMPILE,
                severity=DiagnosticSeverity.ERROR,
                code=ScopeDiagnosticCode.INACCESSIBLE_DECLARATION.value,
                message=(
                    f"{_KIND_LABELS[kind]} '{name}' is not visible from '{consumer_label}'. It "
                    f"is defined at {record.path} with {record.scope.value} scope owned by "
                    f"'{owner}'"
                ),
                resource_type=(
                    compiled_resource_type(resource.kind) if resource is not None else None
                ),
                resource_name=resource.name if resource is not None else None,
                path=Path(consumer_label),
                help=(
                    f"move '{record.path}' to a {role}/ role owned by '{consumer_folder}' or one "
                    f"of its parent folders, or to the project-wide {role}/ when consumers span "
                    "resource trees"
                ),
            ),
        )
    return (UsageRecord(consumer=consumer, declaration=record.identity),)


def declaration_file_expansion(
    *, context: DeclarationExpansionContext, file_path: Path, consumer: DeclarationIdentity
) -> DeclarationExpansionContext:
    """Resolve macros, enums, and constants from a declaration file's own owning folder."""

    resolved: DeclarationExpansionContext = resolve_declaration_expansion(
        context=context, file_path=file_path
    )
    return replace(resolved, declarations=replace(resolved.declarations, consumer=consumer))
