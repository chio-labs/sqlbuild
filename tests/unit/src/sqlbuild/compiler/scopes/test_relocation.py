"""Behavior tests for relocating declarations when a resource moves."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.scopes.main.relocate_declarations_for_move import (
    relocate_declarations_for_move,
)
from sqlbuild.compiler.scopes.models import (
    DeclarationRecord,
    ResourceIdentity,
)
from sqlbuild.compiler.scopes.types import ResourceKind
from tests.unit.src.sqlbuild.compiler.scopes._test_types import RelocationCase
from tests.unit.src.sqlbuild.compiler.scopes.helpers import relocation_index


@pytest.mark.parametrize(
    "test_case",
    (
        RelocationCase(
            description="sole consumer takes the schema and the macro it uses along",
            consumer_paths=("models/staging/orders.sql",),
            destination="models/marts/orders.sql",
            expected_paths=(
                "models/marts/_sqlbuild/_schemas/order_shape.sql",
                "models/marts/_sqlbuild/_macros/cents.py",
            ),
        ),
        RelocationCase(
            description="remaining consumers lift the schema while its macro stays beside it",
            consumer_paths=("models/staging/orders.sql", "models/staging/refunds.sql"),
            destination="models/staging/eu/orders.sql",
            expected_paths=("models/staging/_sqlbuild/schemas/order_shape.sql",),
        ),
        RelocationCase(
            description="consumers spanning the models root use top-level roles",
            consumer_paths=("models/staging/orders.sql", "models/staging/refunds.sql"),
            destination="models/marts/orders.sql",
            expected_paths=("schemas/order_shape.sql", "macros/cents.py"),
        ),
        RelocationCase(
            description="move within the owner changes nothing",
            consumer_paths=("models/staging/orders.sql",),
            destination="models/staging/orders_v2.sql",
            expected_paths=(),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_resource_move_when_relocating_then_declarations_follow_placement(
    test_case: RelocationCase,
) -> None:
    relocated: tuple[DeclarationRecord, ...] | None = relocate_declarations_for_move(
        index=relocation_index(test_case.consumer_paths),
        resource=ResourceIdentity(ResourceKind.MODEL, "orders_0"),
        destination=test_case.destination,
    )

    assert relocated is not None
    assert tuple(item.path for item in relocated) == test_case.expected_paths
