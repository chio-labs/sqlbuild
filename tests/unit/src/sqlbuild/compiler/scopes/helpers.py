"""Fixtures for compiler scope unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredProjectInputs,
    DiscoveredSqlModelFile,
    EnumDeclaration,
)
from sqlbuild.compiler.scopes.main._build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.models import (
    ConstantMetadata,
    DeclarationIdentity,
    DeclarationRecord,
    EnumMemberMetadata,
    EnumMetadata,
    GrantRecord,
    MacroMetadata,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeIndex,
    ScopeLookup,
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


def report_scope_lookup(*, extra_globals: int = 0) -> ScopeLookup:
    """Return representative complete facts for scope report tests."""

    model_root: OwnershipRoot = OwnershipRoot("models", resource_kind=ResourceKind.MODEL)
    global_root: OwnershipRoot = OwnershipRoot("constants", OwnershipRootKind.GLOBAL)
    orders: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, "orders")
    expected: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, "expected_orders")
    resources: tuple[ResourceRecord, ...] = (
        ResourceRecord(orders, "models/staging/orders.sql", model_root),
        ResourceRecord(expected, "models/marts/expected_orders.sql", model_root),
    )
    global_constant: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.CONSTANT, "warehouse_password"),
        "constants/warehouse_password.yml",
        2,
        3,
        ScopeKind.GLOBAL,
        global_root,
        constant=ConstantMetadata("string"),
    )
    inherited: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.ENUM, "order_status"),
        "models/staging/_enums/order_status.sql",
        1,
        1,
        ScopeKind.INHERITED,
        model_root,
        owning_path="models/staging",
        enum=EnumMetadata(
            tuple(
                EnumMemberMetadata(f"STATUS_{index:02d}", f"status_{index:02d}")
                for index in range(25)
            ),
            "VARCHAR",
        ),
    )
    sibling: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.ENUM, "mart_status"),
        "models/marts/_enums/mart_status.sql",
        1,
        1,
        ScopeKind.LOCAL,
        model_root,
        owning_path="models/marts",
    )
    nearby_sibling: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.ENUM, "other_status"),
        "models/other/_enums/other_status.sql",
        1,
        1,
        ScopeKind.LOCAL,
        model_root,
        owning_path="models/other",
    )
    private: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.ENUM, "expected_status", expected),
        "models/marts/expected_orders.sql",
        4,
        2,
        ScopeKind.PRIVATE,
        model_root,
        owning_path="models/marts",
    )
    macro: DeclarationRecord = DeclarationRecord(
        DeclarationIdentity(DeclarationKind.MACRO, "normalize"),
        "macros/normalize.py",
        1,
        1,
        ScopeKind.GLOBAL,
        OwnershipRoot("macros", OwnershipRootKind.GLOBAL),
        macro=MacroMetadata(("value",), (inherited.identity,), "secret-source-digest"),
    )
    generated: tuple[DeclarationRecord, ...] = tuple(
        DeclarationRecord(
            DeclarationIdentity(DeclarationKind.CONSTANT, f"global_{index:05d}"),
            f"constants/generated/{index:05d}.yml",
            1,
            1,
            ScopeKind.GLOBAL,
            global_root,
            constant=ConstantMetadata("integer"),
        )
        for index in range(extra_globals)
    )
    index: ScopeIndex = ScopeIndex(
        ownership_roots=(
            model_root,
            OwnershipRoot("tests/unit", resource_kind=ResourceKind.TEST),
            OwnershipRoot("tests/scenarios", resource_kind=ResourceKind.SCENARIO),
            OwnershipRoot("hooks/sql", resource_kind=ResourceKind.HOOK),
            OwnershipRoot("functions/sql", resource_kind=ResourceKind.FUNCTION),
            OwnershipRoot("audits", resource_kind=ResourceKind.AUDIT),
            OwnershipRoot("sources", resource_kind=ResourceKind.SOURCE),
        ),
        resources=resources,
        declarations=(
            global_constant,
            inherited,
            sibling,
            nearby_sibling,
            private,
            macro,
            *generated,
        ),
        usages=(
            UsageRecord(orders, inherited.identity),
            UsageRecord(orders, macro.identity),
            UsageRecord(orders, sibling.identity, through=expected),
            UsageRecord(expected, private.identity),
        ),
        grants=(GrantRecord(orders, sibling.identity, expected),),
        completeness=ScopeCompleteness(),
    )
    return build_scope_lookup(index=index)
