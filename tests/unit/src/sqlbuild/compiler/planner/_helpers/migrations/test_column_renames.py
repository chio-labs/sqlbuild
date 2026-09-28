"""Unit coverage for recognizing renamed output columns by expression."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.planner._helpers.migrations.column_renames import (
    identical_renames,
    rename_hints,
)
from sqlbuild.compiler.planner._helpers.migrations.projections import (
    parse_query_shape,
    renames_explain_change,
)
from sqlbuild.compiler.planner.models import ColumnRenameHint
from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations._test_types import (
    IdenticalRenameTestCase,
    RenameExplainsChangeTestCase,
    RenameHintTestCase,
    UnreadableQueryShapeTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations.helpers import query_shape

_ORDERS: str = 'FROM __source("raw_orders")'


@pytest.mark.parametrize(
    "test_case",
    [
        IdenticalRenameTestCase(
            description="aliasing a column is a pure rename",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS}",
            expected_renames=(("amount", "revenue"),),
        ),
        IdenticalRenameTestCase(
            description="formatting, comments, and keyword case are ignored",
            previous_sql=f"SELECT order_id, ROUND(amount, 2) AS revenue {_ORDERS}",
            current_sql=(
                "select order_id,\n  round( AMOUNT ,2 )  as net_revenue -- renamed\n"
                'from __source("raw_orders")'
            ),
            expected_renames=(("revenue", "net_revenue"),),
        ),
        IdenticalRenameTestCase(
            description="two columns renamed crosswise pair by expression, not position",
            previous_sql=f"SELECT order_id, amount AS gross, tax AS levy {_ORDERS}",
            current_sql=f"SELECT order_id, tax AS tax_amount, amount AS gross_amount {_ORDERS}",
            expected_renames=(("levy", "tax_amount"), ("gross", "gross_amount")),
        ),
        IdenticalRenameTestCase(
            description="swapped names keep their names, so nothing is renamed",
            previous_sql=f"SELECT order_id, amount AS gross, tax AS levy {_ORDERS}",
            current_sql=f"SELECT order_id, tax AS gross, amount AS levy {_ORDERS}",
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="a near match is not a rename",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, ROUND(amount, 2) AS revenue {_ORDERS}",
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="two removed columns with the same expression are ambiguous",
            previous_sql=f"SELECT order_id, amount AS gross, amount AS total {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS}",
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="two added columns claiming one removed column are ambiguous",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS gross, amount AS revenue {_ORDERS}",
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="declared columns are left to their declaration",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS}",
            excluded=frozenset({"revenue"}),
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="a changed CTE rebinding the same expression is not a rename",
            previous_sql=f"SELECT order_id, order_date, amount {_ORDERS}",
            current_sql=(
                f"WITH changed AS (SELECT order_id, order_date, tax AS amount {_ORDERS}) "
                "SELECT order_id, order_date, amount AS revenue FROM changed"
            ),
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="a new join alongside the rename is not a rename",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=(
                f"SELECT order_id, amount AS revenue {_ORDERS} "
                'JOIN __source("raw_refunds") USING (order_id)'
            ),
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="another projection change alongside the rename is not automatic",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue, tax {_ORDERS}",
            expected_renames=(),
        ),
        IdenticalRenameTestCase(
            description="an ORDER BY that follows the renamed alias is still a rename",
            previous_sql=f"SELECT order_id, amount {_ORDERS} ORDER BY amount",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS} ORDER BY revenue",
            expected_renames=(("amount", "revenue"),),
        ),
        IdenticalRenameTestCase(
            description="a declared rename is part of the proof for a detected one",
            previous_sql=f"SELECT order_id, amount, tax {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue, tax AS levy {_ORDERS}",
            excluded=frozenset({"tax", "levy"}),
            declared={"tax": "levy"},
            expected_renames=(("amount", "revenue"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_previous_and_current_queries_when_detecting_renames_then_returns_unique_matches(
    test_case: IdenticalRenameTestCase,
) -> None:
    renames: tuple[tuple[str, str], ...] = identical_renames(
        previous=query_shape(test_case.previous_sql),
        current=query_shape(test_case.current_sql),
        excluded=test_case.excluded,
        declared=test_case.declared,
    )

    assert renames == test_case.expected_renames


@pytest.mark.parametrize(
    "test_case",
    [
        RenameHintTestCase(
            description="near match points at migrate_from",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, ROUND(amount, 2) AS revenue {_ORDERS}",
            live_columns=frozenset({"order_id", "amount"}),
            expected_hints=(
                "similar to amount; if this is a rename, add revenue (migrate_from amount)",
            ),
        ),
        RenameHintTestCase(
            description="ambiguous identical matches name every candidate",
            previous_sql=f"SELECT order_id, amount AS gross, amount AS total {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS}",
            live_columns=frozenset({"order_id", "gross", "total"}),
            expected_hints=(
                "same expression as gross, total; if this is a rename, add revenue "
                "(migrate_from <column>)",
            ),
        ),
        RenameHintTestCase(
            description="hint disappears once the added column exists",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, ROUND(amount, 2) AS revenue {_ORDERS}",
            live_columns=frozenset({"order_id", "amount", "revenue"}),
            expected_hints=(),
        ),
        RenameHintTestCase(
            description="unrelated new column gets no hint",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, discount * 2 AS promo {_ORDERS}",
            live_columns=frozenset({"order_id", "amount"}),
            expected_hints=(),
        ),
        RenameHintTestCase(
            description="a rebound expression is only similar, never the same",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=(
                f"WITH changed AS (SELECT order_id, tax AS amount {_ORDERS}) "
                "SELECT order_id, amount AS revenue FROM changed"
            ),
            live_columns=frozenset({"order_id", "amount"}),
            expected_hints=(
                "similar to amount; if this is a rename, add revenue (migrate_from amount)",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_changed_columns_when_building_hints_then_suggests_explicit_migrate_from(
    test_case: RenameHintTestCase,
) -> None:
    hints: tuple[ColumnRenameHint, ...] = rename_hints(
        model_name="fct_orders",
        previous=query_shape(test_case.previous_sql),
        current=query_shape(test_case.current_sql),
        excluded=frozenset(),
        live_columns=test_case.live_columns,
    )

    assert tuple(hint.message for hint in hints) == test_case.expected_hints


@pytest.mark.parametrize(
    "test_case",
    [
        RenameExplainsChangeTestCase(
            description="pure rename explains the whole change",
            previous_sql=f"SELECT order_id, amount {_ORDERS} WHERE amount > 0",
            current_sql=f"select order_id, amount as revenue {_ORDERS} where amount > 0",
            renames={"amount": "revenue"},
            expected_explained=True,
        ),
        RenameExplainsChangeTestCase(
            description="an expression change is more than a rename",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, ROUND(amount, 2) AS revenue {_ORDERS}",
            renames={"amount": "revenue"},
            expected_explained=False,
        ),
        RenameExplainsChangeTestCase(
            description="a filter change is more than a rename",
            previous_sql=f"SELECT order_id, amount {_ORDERS}",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS} WHERE amount > 0",
            renames={"amount": "revenue"},
            expected_explained=False,
        ),
        RenameExplainsChangeTestCase(
            description="ORDER BY and QUALIFY references to the renamed alias are equivalent",
            previous_sql=(
                f"SELECT order_id, amount {_ORDERS} "
                "QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY amount) = 1 "
                "ORDER BY amount"
            ),
            current_sql=(
                f"SELECT order_id, amount AS revenue {_ORDERS} "
                "QUALIFY row_number() OVER (PARTITION BY order_id ORDER BY revenue) = 1 "
                "ORDER BY revenue"
            ),
            renames={"amount": "revenue"},
            expected_explained=True,
        ),
        RenameExplainsChangeTestCase(
            description="reordering projections while renaming matches by name",
            previous_sql=f"SELECT order_id, order_date, amount {_ORDERS}",
            current_sql=f"SELECT amount AS revenue, order_id, order_date {_ORDERS}",
            renames={"amount": "revenue"},
            expected_explained=True,
        ),
        RenameExplainsChangeTestCase(
            description="reordering under positional grouping changes the result",
            previous_sql=f"SELECT order_id, sum(amount) AS amount {_ORDERS} GROUP BY 1",
            current_sql=f"SELECT sum(amount) AS revenue, order_id {_ORDERS} GROUP BY 1",
            renames={"amount": "revenue"},
            expected_explained=False,
        ),
        RenameExplainsChangeTestCase(
            description="a WHERE on a renamed alias is not treated as an alias reference",
            previous_sql=f"SELECT order_id, amount {_ORDERS} WHERE amount > 0",
            current_sql=f"SELECT order_id, amount AS revenue {_ORDERS} WHERE revenue > 0",
            renames={"amount": "revenue"},
            expected_explained=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renames_when_comparing_queries_then_reports_whether_they_explain_the_change(
    test_case: RenameExplainsChangeTestCase,
) -> None:
    explained: bool = renames_explain_change(
        previous=query_shape(test_case.previous_sql),
        current=query_shape(test_case.current_sql),
        renames=test_case.renames,
    )

    assert explained is test_case.expected_explained


@pytest.mark.parametrize(
    "test_case",
    [
        UnreadableQueryShapeTestCase(
            description="star projection", query_sql=f"SELECT * {_ORDERS}"
        ),
        UnreadableQueryShapeTestCase(
            description="unnamed expression", query_sql=f"SELECT amount + 1 {_ORDERS}"
        ),
        UnreadableQueryShapeTestCase(
            description="set operation",
            query_sql=f"SELECT amount {_ORDERS} UNION ALL SELECT amount {_ORDERS}",
        ),
        UnreadableQueryShapeTestCase(
            description="duplicate output names",
            query_sql=f"SELECT amount, tax AS amount {_ORDERS}",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_query_without_readable_output_names_when_parsing_then_returns_none(
    test_case: UnreadableQueryShapeTestCase,
) -> None:
    assert (
        parse_query_shape(query_sql=test_case.query_sql, dialect="duckdb")
        is test_case.expected_shape
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
