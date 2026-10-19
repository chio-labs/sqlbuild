from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import RelationInfo, RowDiffResult
from sqlbuild.adapters.sqlite.classes.sqlite_adapter import SqliteAdapter
from tests.integration.src.sqlbuild.adapters.sqlite._test_types import (
    SqliteCollisionTestCase,
    SqliteDecimalDiffTestCase,
    SqliteJanitorViewRenameTestCase,
)
from tests.integration.src.sqlbuild.adapters.sqlite.helpers import (
    fetch_rows,
    recorder,
    render_relations,
    run_sql,
    stage_contract_relation,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteCollisionTestCase(
            description="a main table named like a schema relation is refused",
            first=("staging", "orders"),
            second=("main", "staging__orders"),
            expected_code="A706",
        ),
        SqliteCollisionTestCase(
            description="a schema relation named like a main table is refused",
            first=("main", "staging__orders"),
            second=("staging", "orders"),
            expected_code="A706",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relations_sharing_a_table_name_when_rendering_then_sqlite_refuses(
    test_case: SqliteCollisionTestCase, adapter: SqliteAdapter
) -> None:
    render_relations(adapter=adapter, relations=(test_case.first,))

    with pytest.raises(AdapterUserError) as raised:
        render_relations(adapter=adapter, relations=(test_case.second,))

    assert raised.value.code == test_case.expected_code
    assert "staging__orders" in raised.value.message


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteJanitorViewRenameTestCase(
            description="the janitor's ALTER VIEW statement recreates the view in its schema",
            expected_relations=(
                RelationInfo(None, "analytics", "order_ids__archived", "VIEW"),
                RelationInfo(None, "analytics", "orders", "BASE TABLE"),
            ),
            expected_registry_rows=(
                ("analytics__order_ids__archived", "analytics", "order_ids__archived"),
                ("analytics__orders", "analytics", "orders"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_view_when_running_rename_view_statements_then_sqlite_recreates_it(
    test_case: SqliteJanitorViewRenameTestCase, adapter: SqliteAdapter, connection: Any
) -> None:
    adapter.ensure_schema(
        connection=connection, database=None, schema="analytics", statement_recorder=recorder()
    )
    orders, order_ids, archived = render_relations(
        adapter=adapter,
        relations=(
            ("analytics", "orders"),
            ("analytics", "order_ids"),
            ("analytics", "order_ids__archived"),
        ),
    )
    run_sql(
        adapter=adapter,
        connection=connection,
        statements=(
            f"CREATE TABLE {orders} (order_id INTEGER)",
            f"CREATE VIEW {order_ids} AS SELECT order_id FROM {orders}",
        ),
    )

    run_sql(
        adapter=adapter,
        connection=connection,
        statements=adapter.render_rename_view(origin=str(order_ids), destination=str(archived)),
    )

    assert adapter.list_relations(connection=connection, database=None, schemas=("analytics",)) == (
        test_case.expected_relations
    )
    assert (
        fetch_rows(
            adapter=adapter,
            connection=connection,
            sql="SELECT * FROM _sqlbuild_relations ORDER BY physical_name",
        )
        == test_case.expected_registry_rows
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SqliteDecimalDiffTestCase(
            description="contract decimals enforced from numeric and text inputs diff as equal",
            left_sql="SELECT 1 AS payment_id, 1.5 AS amount UNION ALL SELECT 2, 2",
            right_sql="SELECT 1 AS payment_id, '1.50' AS amount UNION ALL SELECT 2, '2.0'",
            expected_counts=(2, 2, 2, 0),
            expected_rows=((1, "1.50", "1.50"), (2, "2.00", "2.00")),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_identical_decimal_contracts_when_diffing_then_sqlite_reports_no_changes(
    test_case: SqliteDecimalDiffTestCase, adapter: SqliteAdapter, connection: Any
) -> None:
    run_sql(
        adapter=adapter,
        connection=connection,
        statements=(
            "CREATE TABLE numeric_payments (payment_id INTEGER, amount DECIMAL(10,2))",
            f"INSERT INTO numeric_payments {test_case.left_sql}",
        ),
    )
    stage_contract_relation(
        adapter=adapter,
        connection=connection,
        name="payments_left",
        sql="SELECT payment_id, amount FROM numeric_payments",
    )
    stage_contract_relation(
        adapter=adapter, connection=connection, name="payments_right", sql=test_case.right_sql
    )

    result: RowDiffResult = adapter.diff_rows(
        connection=connection,
        left="payments_left",
        right="payments_right",
        unique_key="payment_id",
    )

    assert (
        result.left_count,
        result.right_count,
        result.equal_count,
        result.unequal_count,
    ) == test_case.expected_counts
    assert (
        fetch_rows(
            adapter=adapter,
            connection=connection,
            sql=(
                "SELECT l.payment_id, l.amount, r.amount FROM payments_left AS l "
                "JOIN payments_right AS r USING (payment_id) ORDER BY 1"
            ),
        )
        == test_case.expected_rows
    )
