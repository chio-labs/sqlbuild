"""Tests for column-rename edit planning inside one SQL body."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.refactoring._helpers.text_edits import apply_text_edits
from sqlbuild.compiler.refactoring.models import BodyEdits
from tests.unit.src.sqlbuild.compiler.refactoring._helpers._test_types import ColumnEditTestCase
from tests.unit.src.sqlbuild.compiler.refactoring._helpers.helpers import plan_consumer


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnEditTestCase(
            description="bare projection keeps its output name",
            sql='SELECT o.amount FROM __ref("fact_orders") AS o',
            cascade=False,
            expected_sql='SELECT o.revenue AS amount FROM __ref("fact_orders") AS o',
        ),
        ColumnEditTestCase(
            description="cascade renames a bare projection's output",
            sql='SELECT o.amount FROM __ref("fact_orders") AS o',
            cascade=True,
            expected_sql='SELECT o.revenue FROM __ref("fact_orders") AS o',
            expected_passes_through=True,
        ),
        ColumnEditTestCase(
            description="aliased projection keeps its alias",
            sql='SELECT o.amount AS total FROM __ref("fact_orders") AS o',
            cascade=True,
            expected_sql='SELECT o.revenue AS total FROM __ref("fact_orders") AS o',
        ),
        ColumnEditTestCase(
            description="filter reference is renamed",
            sql='SELECT order_id FROM __ref("fact_orders") WHERE amount > 0',
            cascade=False,
            expected_sql='SELECT order_id FROM __ref("fact_orders") WHERE revenue > 0',
        ),
        ColumnEditTestCase(
            description="same-named column of another relation is untouched",
            sql=(
                'SELECT c.amount FROM __ref("fact_orders") AS o '
                'JOIN __ref("customers") AS c ON o.customer_id = c.customer_id'
            ),
            cascade=False,
            expected_sql=(
                'SELECT c.amount FROM __ref("fact_orders") AS o '
                'JOIN __ref("customers") AS c ON o.customer_id = c.customer_id'
            ),
        ),
        ColumnEditTestCase(
            description="star through a CTE is followed",
            sql='WITH c AS (SELECT * FROM __ref("fact_orders")) SELECT c.amount FROM c',
            cascade=False,
            expected_sql=(
                'WITH c AS (SELECT * FROM __ref("fact_orders")) SELECT c.revenue AS amount FROM c'
            ),
        ),
        ColumnEditTestCase(
            description="root star needs cascade",
            sql='SELECT * FROM __ref("fact_orders")',
            cascade=False,
            expected_sql='SELECT * FROM __ref("fact_orders")',
            expected_manual="rerun with --cascade",
        ),
        ColumnEditTestCase(
            description="root star passes through under cascade",
            sql='SELECT * FROM __ref("fact_orders")',
            cascade=True,
            expected_sql='SELECT * FROM __ref("fact_orders")',
            expected_passes_through=True,
        ),
        ColumnEditTestCase(
            description="USING join is left for the author",
            sql=(
                'SELECT o.order_id FROM __ref("fact_orders") AS o '
                'JOIN __ref("customers") AS c USING (amount)'
            ),
            cascade=False,
            expected_sql=(
                'SELECT o.order_id FROM __ref("fact_orders") AS o '
                'JOIN __ref("customers") AS c USING (amount)'
            ),
            expected_manual="USING or NATURAL join",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_consumer_sql_when_planning_column_rename_then_edits_match(
    test_case: ColumnEditTestCase,
) -> None:
    result: BodyEdits = plan_consumer(sql=test_case.sql, cascade=test_case.cascade)

    assert apply_text_edits(text=test_case.sql, edits=result.edits) == test_case.expected_sql
    assert result.passes_through == test_case.expected_passes_through
    reasons: tuple[str, ...] = tuple(location.reason for location in result.manual)
    assert bool(reasons) == bool(test_case.expected_manual), reasons
    assert all(test_case.expected_manual in reason for reason in reasons), reasons


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
