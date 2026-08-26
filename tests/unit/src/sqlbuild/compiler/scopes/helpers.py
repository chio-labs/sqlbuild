"""Fixtures for compiler scope unit tests."""

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
    ScopeIndex,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    OwnershipRootKind,
    ResourceKind,
    ScopeKind,
)


def scope_index() -> ScopeIndex:
    """Return representative unsorted canonical scope facts."""

    model: ResourceIdentity = ResourceIdentity(kind=ResourceKind.MODEL, name="stg_orders")
    model_root: OwnershipRoot = OwnershipRoot(
        path="models",
        kind=OwnershipRootKind.RESOURCE,
        resource_kind=ResourceKind.MODEL,
    )
    enum: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.ENUM, "order_status"),
        "enums/order_status.sql",
        2,
        1,
        ScopeKind.GLOBAL,
        OwnershipRoot("enums", OwnershipRootKind.GLOBAL),
        enum=EnumMetadata(
            (
                EnumMemberMetadata("OPEN", "OPEN"),
                EnumMemberMetadata("CLOSED", "CLOSED"),
            ),
            "VARCHAR",
        ),
    )
    constant: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.CONSTANT, "minimum_value"),
        "models/staging/_constants/limits.sql",
        8,
        3,
        ScopeKind.INHERITED,
        OwnershipRoot("models", resource_kind=ResourceKind.MODEL),
        owning_path="models/staging",
        constant=ConstantMetadata("integer", render_as="value_list"),
    )
    macro: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.MACRO, "normalize_status"),
        "macros/normalize_status.py",
        1,
        1,
        ScopeKind.GLOBAL,
        OwnershipRoot("macros", OwnershipRootKind.GLOBAL),
        macro=MacroMetadata(("status",), (enum.identity,)),
    )
    return ScopeIndex(
        resources=(ResourceRecord(model, "models/staging/stg_orders.sql", model_root),),
        declarations=(macro, constant, enum),
        usages=(UsageRecord(model, constant.identity), UsageRecord(model, enum.identity)),
        completeness=ScopeCompleteness(runtime_usage=False),
    )
