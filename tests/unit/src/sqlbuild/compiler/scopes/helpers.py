"""Fixtures for compiler scope unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    EnumDeclaration,
)
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
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig


def discovered_inputs(**kwargs: object) -> DiscoveredProjectInputs:
    """Return minimal discovered inputs with selected record tuples."""

    return DiscoveredProjectInputs(
        project_config=ProjectConfig(name="scope_project", adapter="duckdb"),
        local_config=LocalConfig(),
        **kwargs,  # ty: ignore[invalid-argument-type]
    )


def discovered_model(
    *, name: str, path: str, enums: tuple[EnumDeclaration, ...] = ()
) -> DiscoveredSqlModelFile:
    """Return one minimal discovered model."""

    relative: Path = Path(path)
    return DiscoveredSqlModelFile(
        file_path=relative,
        relative_path=relative,
        contents="MODEL(); SELECT 1",
        header_values={"name": name},
        header_column_locations={},
        output_column_locations={},
        query_sql="SELECT 1",
        enum_declarations=enums,
    )


def declaration_record(
    *,
    name: str,
    scope: ScopeKind,
    owner_path: str | None,
    owner: ResourceIdentity | None = None,
    path: str | None = None,
    kind: DeclarationKind = DeclarationKind.ENUM,
) -> DeclarationRecord:
    """Return one minimal declaration record."""

    return DeclarationRecord(
        DeclarationIdentity(kind, name, owner),
        path or f"enums/{name}.sql",
        1,
        1,
        scope,
        OwnershipRoot("models", resource_kind=ResourceKind.MODEL),
        owning_path=owner_path,
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
