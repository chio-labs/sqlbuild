"""Unit coverage for local migration fingerprints."""

from __future__ import annotations

import pytest

from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations._test_types import (
    IneligibleFingerprintTestCase,
    MigrationFingerprintTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations.helpers import (
    BASE_CONFIG,
    ORDERS_SQL,
    model_fingerprint,
)


@pytest.mark.parametrize(
    "test_case",
    [
        MigrationFingerprintTestCase(
            expected_match=False,
            description="alias rename does not rewrite the qualified column name",
            origin_sql='SELECT a.a AS value FROM __ref("stg_orders") a',
            destination_sql='SELECT b.b AS value FROM __ref("stg_orders") b',
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="cte and alias renames keep columns named like the cte",
            origin_sql=(
                'WITH orders AS (SELECT orders FROM __ref("stg_orders")) '
                "SELECT orders.orders, totals.total FROM orders "
                "JOIN (SELECT 1 AS total) AS totals ON TRUE"
            ),
            destination_sql=(
                'WITH customer_orders AS (SELECT orders FROM __ref("stg_orders")) '
                "SELECT customer_orders.orders, sums.total FROM customer_orders "
                "JOIN (SELECT 1 AS total) AS sums ON TRUE"
            ),
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="later cte reading an earlier renamed cte still matches",
            origin_sql=(
                'WITH src AS (SELECT * FROM __ref("stg_orders")), totals AS '
                "(SELECT src.order_id FROM src) SELECT totals.order_id FROM totals"
            ),
            destination_sql=(
                'WITH base AS (SELECT * FROM __ref("stg_orders")), sums AS '
                "(SELECT base.order_id FROM base) SELECT sums.order_id FROM sums"
            ),
        ),
        MigrationFingerprintTestCase(
            expected_match=False,
            description="column named like the renamed cte is still a column",
            origin_sql=(
                'WITH orders AS (SELECT orders FROM __ref("stg_orders")) '
                "SELECT orders.orders FROM orders"
            ),
            destination_sql=(
                'WITH customer_orders AS (SELECT customer_orders FROM __ref("stg_orders")) '
                "SELECT customer_orders.customer_orders FROM customer_orders"
            ),
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="qualified star follows the alias rename",
            origin_sql='SELECT o.* FROM __ref("stg_orders") AS o',
            destination_sql='SELECT customer_order.* FROM __ref("stg_orders") AS customer_order',
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="table_alias_renamed",
            origin_sql=ORDERS_SQL,
            destination_sql=(
                "SELECT customer_order.order_id, customer_order.amount_cents "
                'FROM __ref("stg_orders") AS customer_order'
            ),
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="import_cte_renamed_with_upstream",
            origin_sql=(
                'WITH stg_orders AS (SELECT * FROM __ref("stg_orders")) '
                "SELECT stg_orders.order_id FROM stg_orders"
            ),
            destination_sql=(
                'WITH stg_customer_orders AS (SELECT * FROM __ref("stg_customer_orders")) '
                "SELECT stg_customer_orders.order_id FROM stg_customer_orders"
            ),
            destination_ref_identities={"stg_customer_orders": "stg_orders"},
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="comments_and_formatting",
            origin_sql=ORDERS_SQL,
            destination_sql=(
                "-- orders with amounts\n"
                "SELECT\n    o.order_id,\n    /* cents */ o.amount_cents\n"
                'FROM __ref("stg_orders")   AS o\n'
            ),
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="storage_config_changed",
            origin_sql=ORDERS_SQL,
            destination_sql=ORDERS_SQL,
            destination_config={**BASE_CONFIG, "incremental_strategy": "merge", "lookback": "1d"},
        ),
        MigrationFingerprintTestCase(
            expected_match=True,
            description="cursor_inputs_follow_renamed_upstream",
            origin_sql=ORDERS_SQL,
            destination_sql=ORDERS_SQL.replace("stg_orders", "stg_customer_orders"),
            origin_config={**BASE_CONFIG, "cursor_inputs": {"stg_orders": "order_date"}},
            destination_config={
                **BASE_CONFIG,
                "cursor_inputs": {"stg_customer_orders": "order_date"},
            },
            destination_ref_identities={"stg_customer_orders": "stg_orders"},
        ),
        MigrationFingerprintTestCase(
            expected_match=False,
            description="filter_added",
            origin_sql=ORDERS_SQL,
            destination_sql=f"{ORDERS_SQL} WHERE o.amount_cents > 0",
        ),
        MigrationFingerprintTestCase(
            expected_match=False,
            description="unresolved_upstream_rename",
            origin_sql=ORDERS_SQL,
            destination_sql=ORDERS_SQL.replace("stg_orders", "stg_customer_orders"),
        ),
        MigrationFingerprintTestCase(
            expected_match=False,
            description="column_renamed",
            origin_sql=ORDERS_SQL,
            destination_sql=(
                'SELECT o.order_id, o.amount_cents AS total_cents FROM __ref("stg_orders") AS o'
            ),
        ),
        MigrationFingerprintTestCase(
            expected_match=False,
            description="unique_key_changed",
            origin_sql=ORDERS_SQL,
            destination_sql=ORDERS_SQL,
            destination_config={**BASE_CONFIG, "unique_key": "amount_cents"},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_renamed_definition_when_fingerprinting_then_matches_only_equivalent_logic(
    test_case: MigrationFingerprintTestCase,
) -> None:
    origin: str | None = model_fingerprint(
        model_name="stg_orders",
        query_sql=test_case.origin_sql,
        config=test_case.origin_config,
        ref_identities={},
    )
    destination: str | None = model_fingerprint(
        model_name="stg_customer_orders",
        query_sql=test_case.destination_sql,
        config=test_case.destination_config,
        ref_identities=test_case.destination_ref_identities,
    )

    assert origin is not None
    assert destination is not None
    assert (origin == destination) is test_case.expected_match


@pytest.mark.parametrize(
    "test_case",
    [
        IneligibleFingerprintTestCase(
            description="unparseable query has no fingerprint",
            query_sql="SELECT FROM WHERE (",
            expected_fingerprint=None,
        ),
        IneligibleFingerprintTestCase(
            description="nested with shadows an outer physical relation",
            query_sql=(
                "WITH wrapper AS (WITH a AS (SELECT 1 AS value) SELECT value FROM a) "
                "SELECT value FROM a"
            ),
            expected_fingerprint=None,
        ),
        IneligibleFingerprintTestCase(
            description="with nested in a subquery",
            query_sql="SELECT x FROM (WITH q AS (SELECT 1 AS x) SELECT x FROM q) AS s",
            expected_fingerprint=None,
        ),
        IneligibleFingerprintTestCase(
            description="cte body reads the physical relation it shadows",
            query_sql="WITH orders AS (SELECT * FROM orders) SELECT * FROM orders",
            expected_fingerprint=None,
        ),
        IneligibleFingerprintTestCase(
            description="cte body reads a later cte name",
            query_sql=(
                "WITH totals AS (SELECT * FROM orders), orders AS (SELECT 1 AS x) "
                "SELECT * FROM totals"
            ),
            expected_fingerprint=None,
        ),
        IneligibleFingerprintTestCase(
            description="recursive with",
            query_sql="WITH RECURSIVE n AS (SELECT 1 AS x) SELECT x FROM n",
            expected_fingerprint=None,
        ),
        IneligibleFingerprintTestCase(
            description="alias reuses a physical relation name",
            query_sql="SELECT o.x FROM orders AS o JOIN o ON TRUE",
            expected_fingerprint=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unparseable_or_ambiguous_sql_when_fingerprinting_then_returns_none(
    test_case: IneligibleFingerprintTestCase,
) -> None:
    fingerprint: str | None = model_fingerprint(
        model_name="stg_orders",
        query_sql=test_case.query_sql,
        config=BASE_CONFIG,
        ref_identities={},
    )

    assert fingerprint == test_case.expected_fingerprint


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
