from __future__ import annotations

import pytest

from sqlbuild.executor.janitor._helpers.relation_addressing import (
    case_colliding_names,
    unaddressable_relation_reason,
)
from sqlbuild.executor.janitor.constants import (
    CASE_COLLISION_REASON,
    UNQUOTED_ADDRESSING_REASON,
)
from tests.unit.src.sqlbuild.executor.janitor._helpers._test_types import (
    RelationAddressingTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RelationAddressingTestCase(
            description="plain lowercase name is addressable",
            name="old_orders",
            listing=("old_orders", "customers"),
            expected_reason=None,
        ),
        RelationAddressingTestCase(
            description="lowercase name with digits dollar and leading underscore is addressable",
            name="_orders$2026",
            listing=("_orders$2026",),
            expected_reason=None,
        ),
        RelationAddressingTestCase(
            description="uppercase name is skipped",
            name="OLD_ORDERS",
            listing=("OLD_ORDERS",),
            expected_reason=UNQUOTED_ADDRESSING_REASON,
        ),
        RelationAddressingTestCase(
            description="mixed-case name is skipped",
            name="OldOrders",
            listing=("OldOrders",),
            expected_reason=UNQUOTED_ADDRESSING_REASON,
        ),
        RelationAddressingTestCase(
            description="name with punctuation is skipped",
            name="old-orders;drop",
            listing=("old-orders;drop",),
            expected_reason=UNQUOTED_ADDRESSING_REASON,
        ),
        RelationAddressingTestCase(
            description="name with a leading digit is skipped",
            name="2026_orders",
            listing=("2026_orders",),
            expected_reason=UNQUOTED_ADDRESSING_REASON,
        ),
        RelationAddressingTestCase(
            description="lowercase name colliding case-insensitively is skipped",
            name="old_orders",
            listing=("old_orders", "OLD_ORDERS"),
            expected_reason=CASE_COLLISION_REASON,
        ),
        RelationAddressingTestCase(
            description="uppercase side of a case collision is skipped",
            name="OLD_ORDERS",
            listing=("old_orders", "OLD_ORDERS"),
            expected_reason=UNQUOTED_ADDRESSING_REASON,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_catalog_name_when_checking_addressing_then_returns_expected_reason(
    test_case: RelationAddressingTestCase,
) -> None:
    reason: str | None = unaddressable_relation_reason(
        name=test_case.name, colliding_names=case_colliding_names(test_case.listing)
    )

    assert reason == test_case.expected_reason
