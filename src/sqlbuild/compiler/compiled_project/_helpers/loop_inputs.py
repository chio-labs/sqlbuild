"""Project declarations and scope classes the native model loop resolves models with."""

from sqlbuild.compiler.compile.models import DeclarationScopeResolver, ModelInputBuildContext
from sqlbuild.compiler.discovery.models import EnumDeclaration
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    ResourceIdentity,
    VisibilityRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    ScopeKind,
    VisibilityReason,
)


def schema_records(resolver: DeclarationScopeResolver | None) -> dict[str, DeclarationRecord]:
    """Each project-owned schema's first declaration record, as `named_declaration_record` reads."""

    if resolver is None:
        return {}
    records: dict[str, DeclarationRecord] = {}
    for identity, declarations in resolver.lookup.declarations.items():
        if identity.kind is DeclarationKind.SCHEMA and identity.owner is None and declarations:
            records[identity.name] = declarations[0]
    return records


def schema_enums(resolver: DeclarationScopeResolver | None) -> dict[str, EnumDeclaration]:
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


def visibility_classes(
    *, context: ModelInputBuildContext, visible_declarations: object
) -> dict[str, object]:
    """What the loop resolves each model's visible declarations from."""

    resolver: DeclarationScopeResolver | None = context.declaration_resolver
    return {
        "resolver": resolver,
        "projects": resolver is not None and bool(resolver.lookup.index.declarations),
        "resource_specific": (
            frozenset(
                declaration.identity.owner
                for declaration in resolver.lookup.index.declarations
                if declaration.scope is ScopeKind.PRIVATE and declaration.identity.owner is not None
            )
            | frozenset(resolver.lookup.grants_by_resource)
            if resolver is not None
            else frozenset()
        ),
        "public_enums": context.public_enums,
        "public_constants": context.public_constants,
        "visible_declarations": visible_declarations,
        "resource_identity": ResourceIdentity,
        "declaration_identity": DeclarationIdentity,
        "model_kind": ResourceKind.MODEL,
        "enum_kind": DeclarationKind.ENUM,
        "constant_kind": DeclarationKind.CONSTANT,
        "private_owner": VisibilityReason.PRIVATE_OWNER,
        "visibility_record": VisibilityRecord,
    }
