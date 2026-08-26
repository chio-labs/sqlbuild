"""Default metadata projection implementation."""

from __future__ import annotations

from sqlbuild.compiler.scopes._helpers.identities import format_identity
from sqlbuild.compiler.scopes.constants import SCOPE_METADATA_SCHEMA_VERSION
from sqlbuild.compiler.scopes.models import (
    DeclarationRecord,
    GrantRecord,
    ResourceRecord,
    ScopeIndex,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import JsonValue


def build_projection(*, index: ScopeIndex) -> dict[str, JsonValue]:
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
        "declarations": [declaration_projection(record=record) for record in declarations],
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


def declaration_projection(*, record: DeclarationRecord) -> dict[str, JsonValue]:
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
