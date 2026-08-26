"""Safe deterministic projections for scope query results."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes._helpers.paths import normalize_path
from sqlbuild.compiler.scopes.constants import (
    DEFAULT_ENUM_MEMBER_PREVIEW,
    SCOPE_METADATA_SCHEMA_VERSION,
)
from sqlbuild.compiler.scopes.exceptions import InvalidScopePathError
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    DeclarationReport,
    GrantRecord,
    ResourceIdentity,
    ResourceRecord,
    ScopeDiagnostic,
    ScopeIndex,
    ScopeLookup,
    SourceLocation,
    UsageRecord,
    VisibilityProvenance,
)
from sqlbuild.compiler.scopes.types import JsonValue, ScopeKind


def build_projection(*, index: ScopeIndex) -> dict[str, JsonValue]:
    """Project deterministic value-free metadata from one canonical index."""

    declarations: list[DeclarationRecord] = sorted(
        index.declarations,
        key=lambda item: (
            format_identity(identity=item.identity),
            item.path,
            item.line,
            item.column,
        ),
    )
    resources: list[ResourceRecord] = sorted(
        index.resources,
        key=lambda item: (format_identity(identity=item.identity), item.path),
    )
    grants: list[GrantRecord] = sorted(
        index.grants,
        key=lambda item: (
            format_identity(identity=item.resource),
            format_identity(identity=item.declaration),
            format_identity(identity=item.through),
            item.kind.value,
        ),
    )
    usages: list[UsageRecord] = sorted(
        index.usages,
        key=lambda item: (
            format_identity(identity=item.consumer),
            format_identity(identity=item.declaration),
            item.kind.value,
            format_identity(identity=item.through) if item.through is not None else "",
            item.enum_member or "",
        ),
    )
    return {
        "schema_version": SCOPE_METADATA_SCHEMA_VERSION,
        "ownership_roots": [
            {
                "path": root.path,
                "resource_kind": (
                    root.resource_kind.value if root.resource_kind is not None else None
                ),
            }
            for root in sorted(
                index.ownership_roots,
                key=lambda item: (
                    item.path,
                    item.resource_kind.value if item.resource_kind is not None else "",
                ),
            )
        ],
        "resources": [
            {
                "identity": format_identity(identity=record.identity),
                "kind": record.identity.kind.value,
                "name": record.identity.name,
                "path": record.path,
                "ownership_root": record.ownership_root.path,
                "ownership_root_kind": (
                    record.ownership_root.resource_kind.value
                    if record.ownership_root.resource_kind is not None
                    else None
                ),
            }
            for record in resources
        ],
        "declarations": [_declaration_projection(record=record) for record in declarations],
        "grants": [
            {
                "resource": format_identity(identity=record.resource),
                "declaration": format_identity(identity=record.declaration),
                "through": format_identity(identity=record.through),
                "kind": record.kind.value,
            }
            for record in grants
        ],
        "usages": [
            {
                "consumer": format_identity(identity=record.consumer),
                "declaration": format_identity(identity=record.declaration),
                "kind": record.kind.value,
                "through": (
                    format_identity(identity=record.through) if record.through is not None else None
                ),
                "enum_member": record.enum_member,
            }
            for record in usages
        ],
        "complete": index.completeness.complete,
        "completeness": {
            section.value: complete for section, complete in index.completeness.as_mapping().items()
        },
        "diagnostics": [
            {
                "code": diagnostic.code.value,
                "message": diagnostic.message,
                "severity": diagnostic.severity.value,
                "path": diagnostic.path,
                "line": diagnostic.line,
                "column": diagnostic.column,
                "declaration": (
                    format_identity(identity=diagnostic.declaration)
                    if diagnostic.declaration is not None
                    else None
                ),
                "resource": (
                    format_identity(identity=diagnostic.resource)
                    if diagnostic.resource is not None
                    else None
                ),
            }
            for diagnostic in sorted(
                index.diagnostics,
                key=lambda item: (
                    item.path or "",
                    item.line or 0,
                    item.column or 0,
                    item.code.value,
                ),
            )
        ],
    }


def _declaration_projection(*, record: DeclarationRecord) -> dict[str, JsonValue]:
    metadata: dict[str, JsonValue] = {}
    if record.macro is not None:
        metadata["macro"] = {
            "parameters": list(record.macro.parameters),
            "dependencies": sorted(
                format_identity(identity=identity) for identity in record.macro.dependencies
            ),
            "source_digest": record.macro.source_digest,
        }
    if record.enum is not None:
        metadata["enum"] = {
            "members": [
                {"name": member.name, "value": member.value} for member in record.enum.members
            ],
            "scalar_type": record.enum.scalar_type,
        }
    if record.constant is not None:
        metadata["constant"] = {
            "logical_type": record.constant.logical_type,
            "collection_kind": record.constant.collection_kind,
            "item_count": record.constant.item_count,
            "nullable": record.constant.nullable,
            "render_as": record.constant.render_as,
        }
    return {
        "identity": format_identity(identity=record.identity),
        "kind": record.identity.kind.value,
        "name": record.identity.name,
        "owner": (
            format_identity(identity=record.identity.owner)
            if record.identity.owner is not None
            else None
        ),
        "path": record.path,
        "line": record.line,
        "column": record.column,
        "scope": record.scope.value,
        "ownership_root": record.ownership_root.path,
        "owning_path": record.owning_path,
        "metadata": metadata,
    }


def declaration_report(
    *,
    lookup: ScopeLookup,
    record: DeclarationRecord,
    visibility: VisibilityProvenance | None = None,
    inaccessible_reason: str | None = None,
) -> DeclarationReport:
    """Project a declaration without source, values, callables, or process data."""

    usages: tuple[UsageRecord, ...] = lookup.usages_by_declaration.get(record.identity, ())
    consumers: tuple[str, ...] = tuple(
        sorted({format_identity(identity=usage.consumer) for usage in usages})
    )
    dependencies: tuple[str, ...] = ()
    metadata: list[tuple[str, object]] = []
    if record.macro is not None:
        dependencies = tuple(
            sorted(format_identity(identity=item) for item in record.macro.dependencies)
        )
        metadata.extend(
            (("parameters", record.macro.parameters), ("dependency_count", len(dependencies)))
        )
    if record.enum is not None:
        metadata.extend(
            (
                ("scalar_type", record.enum.scalar_type),
                (
                    "members",
                    tuple(
                        member.name for member in record.enum.members[:DEFAULT_ENUM_MEMBER_PREVIEW]
                    ),
                ),
                ("member_count", len(record.enum.members)),
                (
                    "members_truncated",
                    len(record.enum.members) > DEFAULT_ENUM_MEMBER_PREVIEW,
                ),
            )
        )
    if record.constant is not None:
        metadata.extend(
            (
                ("logical_type", record.constant.logical_type),
                ("collection_kind", record.constant.collection_kind),
                ("item_count", record.constant.item_count),
                ("nullable", record.constant.nullable),
                ("render_as", record.constant.render_as),
            )
        )
    grants: tuple[str, ...] = tuple(
        sorted(
            {
                format_identity(identity=grant.resource)
                for grant in lookup.index.grants
                if grant.declaration == record.identity
            }
        )
    )
    required_scope, required_path, promotion = required_placement(lookup=lookup, record=record)
    return DeclarationReport(
        identity=format_identity(identity=record.identity),
        kind=record.identity.kind.value,
        name=record.identity.name,
        owner=(
            format_identity(identity=record.identity.owner)
            if record.identity.owner is not None
            else None
        ),
        definition=SourceLocation(safe_scope_path(path=record.path), record.line, record.column),
        scope=record.scope.value,
        owning_path=record.owning_path,
        visibility=visibility,
        inaccessible_reason=inaccessible_reason,
        metadata=tuple(metadata),
        consumers=consumers,
        dependencies=dependencies,
        grants=grants,
        required_scope=required_scope,
        required_path=required_path,
        promotion_impact=promotion,
    )


def required_placement(
    *, lookup: ScopeLookup, record: DeclarationRecord
) -> tuple[str | None, str | None, tuple[str, ...]]:
    """Read exact placement from canonical facts using the placement helper's anchor rules."""

    if not lookup.usages_by_declaration.get(record.identity):
        return None, None, ()
    from sqlbuild.compiler.scopes._helpers.placement import resolve_required_placement

    resolved: tuple[ScopeKind, str | None, tuple[str, ...]] | None = resolve_required_placement(
        index=lookup.index, declaration=record.identity
    )
    if resolved is None:
        return None, None, ()
    scope, path, consumers = resolved
    current_path: str = record.owning_path or record.ownership_root.path
    promotion: tuple[str, ...] = ()
    if scope.value != record.scope.value or path != current_path:
        promotion = consumers
    return scope.value, path, promotion


def diagnostic_projection(*, diagnostic: ScopeDiagnostic) -> dict[str, object]:
    """Return a safe JSON-ready diagnostic projection."""

    return {
        "code": diagnostic.code.value,
        "message": diagnostic.message.replace("\x1b", ""),
        "severity": diagnostic.severity.value,
        "path": safe_scope_path(path=diagnostic.path) if diagnostic.path is not None else None,
        "line": diagnostic.line,
        "column": diagnostic.column,
        "declaration": _identity_text(identity=diagnostic.declaration),
        "resource": _identity_text(identity=diagnostic.resource),
    }


def records_for_identities(
    *, lookup: ScopeLookup, identities: Iterable[DeclarationIdentity]
) -> tuple[DeclarationRecord, ...]:
    """Return every known duplicate match in stable identity/location order."""

    records: list[DeclarationRecord] = []
    for identity in identities:
        records.extend(lookup.declarations.get(identity, ()))
    return tuple(
        sorted(
            records,
            key=lambda item: (
                format_identity(identity=item.identity),
                item.path,
                item.line,
                item.column,
            ),
        )
    )


def safe_scope_path(*, path: str) -> str:
    """Return a normalized relative path without leaking invalid absolute input."""

    try:
        return normalize_path(path=path)
    except InvalidScopePathError:
        return "<invalid-project-relative-path>"


def _identity_text(*, identity: DeclarationIdentity | object | None) -> str | None:
    if identity is None:
        return None
    typed_identity: DeclarationIdentity | ResourceIdentity = cast(
        "DeclarationIdentity | ResourceIdentity", identity
    )
    return format_identity(identity=typed_identity)
