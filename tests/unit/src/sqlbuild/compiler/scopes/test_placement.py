"""Behavior tests for complete declaration usage placement validation."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.scopes.main._get_placement_validated_scope_index import (
    get_placement_validated_scope_index,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationIdentity,
    DeclarationRecord,
    OwnershipRoot,
    ResourceIdentity,
    ResourceRecord,
    ScopeCompleteness,
    ScopeIndex,
    UsageRecord,
)
from sqlbuild.compiler.scopes.types import (
    DeclarationKind,
    ResourceKind,
    ScopeDiagnosticCode,
    ScopeKind,
)
from tests.unit.src.sqlbuild.compiler.scopes._test_types import PlacementValidationCase


@pytest.mark.parametrize(
    "test_case",
    (
        PlacementValidationCase(
            "unused global is rejected",
            ScopeKind.GLOBAL,
            None,
            "constants/limit.sql",
            "constants",
            None,
            (),
            (ScopeDiagnosticCode.UNUSED_DECLARATION,),
        ),
        PlacementValidationCase(
            "exact local is accepted",
            ScopeKind.LOCAL,
            "models/domain",
            "models/domain/_local_constants/limit.sql",
            "models",
            ResourceKind.MODEL,
            ("models/domain/orders.sql",),
            (),
        ),
        PlacementValidationCase(
            "local needed by descendant",
            ScopeKind.LOCAL,
            "models/domain",
            "models/domain/_local_constants/limit.sql",
            "models",
            ResourceKind.MODEL,
            ("models/domain/child/orders.sql",),
            (ScopeDiagnosticCode.LOCAL_NEEDED_BY_DESCENDANT,),
        ),
        PlacementValidationCase(
            "inherited multi child lca is accepted",
            ScopeKind.INHERITED,
            "models/domain",
            "models/domain/_constants/limit.sql",
            "models",
            ResourceKind.MODEL,
            ("models/domain/a/orders.sql", "models/domain/b/customers.sql"),
            (),
        ),
        PlacementValidationCase(
            "inherited at one consumer directory is over broad",
            ScopeKind.INHERITED,
            "models/domain",
            "models/domain/_constants/limit.sql",
            "models",
            ResourceKind.MODEL,
            ("models/domain/orders.sql",),
            (ScopeDiagnosticCode.OVER_BROAD_INHERITED,),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_complete_usage_when_validating_then_exact_placement_is_enforced(
    test_case: PlacementValidationCase,
) -> None:
    declaration_identity: DeclarationIdentity = DeclarationIdentity(
        DeclarationKind.CONSTANT, "limit"
    )
    declaration: DeclarationRecord = DeclarationRecord(
        identity=declaration_identity,
        path=test_case.declaration_path,
        line=1,
        column=1,
        scope=test_case.declaration_scope,
        ownership_root=OwnershipRoot(
            test_case.ownership_root, resource_kind=test_case.root_resource_kind
        ),
        owning_path=test_case.declaration_owner,
    )
    resources: tuple[ResourceRecord, ...] = tuple(
        ResourceRecord(
            identity=ResourceIdentity(ResourceKind.MODEL, f"model_{index}"),
            path=path,
            ownership_root=OwnershipRoot("models", resource_kind=ResourceKind.MODEL),
        )
        for index, path in enumerate(test_case.consumer_paths)
    )
    usages: tuple[UsageRecord, ...] = tuple(
        UsageRecord(resource.identity, declaration_identity) for resource in resources
    )

    result: ScopeIndex = get_placement_validated_scope_index(
        index=ScopeIndex(
            resources=resources,
            declarations=(declaration,),
            usages=usages,
            completeness=ScopeCompleteness(runtime_usage=True, placement=False),
        )
    )

    assert tuple(diagnostic.code for diagnostic in result.diagnostics) == test_case.expected_codes
    assert result.completeness.runtime_usage
    assert result.completeness.placement


@pytest.mark.parametrize(
    "test_case",
    (
        PlacementValidationCase(
            "relationship",
            ScopeKind.LOCAL,
            "models/domain",
            "models/domain/_local_enums/state.sql",
            "models",
            ResourceKind.MODEL,
            (),
            (),
            (ScopeDiagnosticCode.REQUIRES_GLOBAL_PLACEMENT,),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_relationship_and_cross_root_usages_when_validating_then_through_models_anchor_placement(
    test_case: PlacementValidationCase,
) -> None:
    declaration_identity: DeclarationIdentity = DeclarationIdentity(DeclarationKind.ENUM, "state")
    test_identity: ResourceIdentity = ResourceIdentity(ResourceKind.TEST, "check")
    model_identity: ResourceIdentity = ResourceIdentity(ResourceKind.MODEL, "orders")
    declaration: DeclarationRecord = DeclarationRecord(
        declaration_identity,
        test_case.declaration_path,
        1,
        1,
        ScopeKind.LOCAL,
        OwnershipRoot("models", resource_kind=ResourceKind.MODEL),
        owning_path="models/domain",
    )
    resources: tuple[ResourceRecord, ...] = (
        ResourceRecord(
            test_identity,
            "tests/unit/check.sql",
            OwnershipRoot("tests/unit", resource_kind=ResourceKind.TEST),
        ),
        ResourceRecord(
            model_identity,
            "models/domain/orders.sql",
            OwnershipRoot("models", resource_kind=ResourceKind.MODEL),
        ),
    )

    relationship_only: ScopeIndex = get_placement_validated_scope_index(
        index=ScopeIndex(
            resources=resources,
            declarations=(declaration,),
            usages=(UsageRecord(test_identity, declaration_identity, through=model_identity),),
        )
    )
    direct_and_relationship: ScopeIndex = get_placement_validated_scope_index(
        index=ScopeIndex(
            resources=resources,
            declarations=(declaration,),
            usages=(
                UsageRecord(test_identity, declaration_identity, through=model_identity),
                UsageRecord(test_identity, declaration_identity),
            ),
        )
    )

    assert relationship_only.diagnostics == ()
    assert (
        tuple(item.code for item in direct_and_relationship.diagnostics)
        == test_case.expected_direct_codes
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
