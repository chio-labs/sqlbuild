"""Tests for canonical immutable lookup and safe metadata projection."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from types import MappingProxyType
from typing import Any, cast

import pytest

from sqlbuild.compiler.scopes.main.build_scope_lookup import build_scope_lookup
from sqlbuild.compiler.scopes.main.scope_metadata import scope_metadata_projection
from sqlbuild.compiler.scopes.models import (
    DeclarationRecord,
    ResourceIdentity,
    ScopeIndex,
    ScopeLookup,
)
from sqlbuild.compiler.scopes.types import (
    ResourceKind,
)
from tests.unit.src.sqlbuild.compiler.scopes._test_types import (
    ExpectedBooleanCase,
    ExpectedErrorCase,
)
from tests.unit.src.sqlbuild.compiler.scopes.helpers import scope_index


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanCase("canonical_order", True)],
    ids=lambda case: case.description,
)
def test_given_unsorted_index_when_building_lookup_then_records_and_edges_are_canonical(
    test_case: ExpectedBooleanCase,
) -> None:
    lookup: ScopeLookup = build_scope_lookup(index=scope_index())

    assert (
        [record.identity.name for record in lookup.index.declarations]
        == [
            "minimum_value",
            "order_status",
            "normalize_status",
        ]
    ) is test_case.expected_result
    model: ResourceIdentity = ResourceIdentity(kind=ResourceKind.MODEL, name="stg_orders")
    assert [usage.declaration.name for usage in lookup.usages_by_consumer[model]] == [
        "minimum_value",
        "order_status",
    ]


@pytest.mark.parametrize(
    "test_case",
    [ExpectedErrorCase("mapping_proxy", TypeError)],
    ids=lambda case: case.description,
)
def test_given_scope_lookup_when_mutating_mapping_then_mapping_is_immutable(
    test_case: ExpectedErrorCase,
) -> None:
    lookup: ScopeLookup = build_scope_lookup(index=scope_index())

    assert isinstance(lookup.resources, MappingProxyType)
    with pytest.raises(test_case.expected_error):
        lookup.resources[ResourceIdentity(kind=ResourceKind.MODEL, name="other")] = next(  # ty: ignore[invalid-assignment]
            iter(lookup.resources.values())
        )


@pytest.mark.parametrize(
    "test_case",
    [ExpectedErrorCase("frozen_record", FrozenInstanceError)],
    ids=lambda case: case.description,
)
def test_given_frozen_scope_record_when_mutating_field_then_record_is_immutable(
    test_case: ExpectedErrorCase,
) -> None:
    record: DeclarationRecord = scope_index().declarations[0]

    with pytest.raises(test_case.expected_error):
        record.path = "changed.sql"  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanCase("byte_deterministic", True)],
    ids=lambda case: case.description,
)
def test_given_equivalent_indexes_when_serializing_then_json_is_byte_deterministic(
    test_case: ExpectedBooleanCase,
) -> None:
    index: ScopeIndex = scope_index()
    reversed_index: ScopeIndex = ScopeIndex(
        resources=tuple(reversed(index.resources)),
        declarations=tuple(reversed(index.declarations)),
        usages=tuple(reversed(index.usages)),
        completeness=index.completeness,
    )

    assert (
        scope_metadata_projection(index=index) == scope_metadata_projection(index=reversed_index)
    ) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanCase("value_safe_projection", False)],
    ids=lambda case: case.description,
)
def test_given_typed_constant_when_projecting_default_metadata_then_value_is_absent(
    test_case: ExpectedBooleanCase,
) -> None:
    projection: dict[str, Any] = cast(
        dict[str, Any], scope_metadata_projection(index=scope_index())
    )
    constant: dict[str, Any] = projection["declarations"][0]

    assert projection["schema_version"] == 2
    assert constant["role"] == "constants"
    assert constant["visibility"] == "descendant_public"
    assert constant["role_root"] == "models/staging/constants"
    assert constant["bucket_path"] is None
    assert constant["metadata"]["constant"] == {
        "logical_type": "integer",
        "collection_kind": None,
        "item_count": None,
        "nullable": False,
        "render_as": "value_list",
    }
    assert projection["complete"] is test_case.expected_result
    assert projection["completeness"]["runtime_usage"] is test_case.expected_result


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
