from __future__ import annotations

import pytest

from sqlbuild.adapters.clickhouse._helpers.output_columns import alias_qualified_columns
from tests.unit.src.sqlbuild.adapters.clickhouse._test_types import AliasQualifiedColumnsTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        AliasQualifiedColumnsTestCase(
            description="a joined column named after its alias",
            actual=("o.order_id", "quantity", "payment_amount_cents"),
            expected=("order_id", "quantity", "payment_amount_cents"),
            expected_pairs=(("o.order_id", "order_id"),),
        ),
        AliasQualifiedColumnsTestCase(
            description="matching names",
            actual=("order_id", "quantity"),
            expected=("order_id", "quantity"),
            expected_pairs=(),
        ),
        AliasQualifiedColumnsTestCase(
            description="a deliberate dotted name the analysis also expects",
            actual=("order.id", "quantity"),
            expected=("order.id", "quantity"),
            expected_pairs=(),
        ),
        AliasQualifiedColumnsTestCase(
            description="a dotted name whose suffix the query also produces",
            actual=("o.order_id", "order_id"),
            expected=("order_id",),
            expected_pairs=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_output_columns_when_comparing_with_analysis_then_alias_named_columns_are_found(
    test_case: AliasQualifiedColumnsTestCase,
) -> None:
    assert (
        alias_qualified_columns(actual=test_case.actual, expected=test_case.expected)
        == test_case.expected_pairs
    )
