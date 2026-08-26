"""Tests for qualified resource and declaration identities."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.scopes.exceptions import InvalidQualifiedIdentityError
from sqlbuild.compiler.scopes.main._parse_qualified_identity import parse_qualified_identity
from sqlbuild.compiler.scopes.main._qualified_identity_text import format_qualified_identity
from sqlbuild.compiler.scopes.models import DeclarationIdentity, ResourceIdentity
from sqlbuild.compiler.scopes.types import DeclarationKind, ResourceKind
from tests.unit.src.sqlbuild.compiler.scopes._test_types import (
    InvalidIdentityCase,
    QualifiedIdentityCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        QualifiedIdentityCase(
            description="resource",
            text="model:stg_orders",
            expected_identity=ResourceIdentity(kind=ResourceKind.MODEL, name="stg_orders"),
        ),
        QualifiedIdentityCase(
            description="public_declaration",
            text="enum:order_status",
            expected_identity=DeclarationIdentity(kind=DeclarationKind.ENUM, name="order_status"),
        ),
        QualifiedIdentityCase(
            description="private_owner_qualified_declaration",
            text="constant:model:stg_orders._minimum_value",
            expected_identity=DeclarationIdentity(
                kind=DeclarationKind.CONSTANT,
                name="_minimum_value",
                owner=ResourceIdentity(kind=ResourceKind.MODEL, name="stg_orders"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_qualified_identity_when_parsing_and_formatting_then_round_trips(
    test_case: QualifiedIdentityCase,
) -> None:
    parsed: ResourceIdentity | DeclarationIdentity = parse_qualified_identity(value=test_case.text)

    assert parsed == test_case.expected_identity
    assert format_qualified_identity(identity=parsed) == test_case.text


@pytest.mark.parametrize(
    "test_case",
    [
        QualifiedIdentityCase(
            "cross_kind", "order_status", DeclarationIdentity(DeclarationKind.ENUM, "order_status")
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cross_kind_same_name_when_constructing_identities_then_they_remain_distinct(
    test_case: QualifiedIdentityCase,
) -> None:
    identities: set[DeclarationIdentity] = {
        DeclarationIdentity(kind=kind, name="order_status") for kind in DeclarationKind
    }

    assert test_case.expected_identity in identities


@pytest.mark.parametrize(
    "test_case",
    [InvalidIdentityCase("bare_name", "stg_orders", InvalidQualifiedIdentityError)],
    ids=lambda case: case.description,
)
def test_given_bare_name_when_parsing_then_rejects_unqualified_identity(
    test_case: InvalidIdentityCase,
) -> None:
    with pytest.raises(test_case.expected_error, match="kind-qualified"):
        parse_qualified_identity(value=test_case.value)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
