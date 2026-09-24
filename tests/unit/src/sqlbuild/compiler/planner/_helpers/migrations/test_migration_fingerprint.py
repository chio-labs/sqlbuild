"""Unit coverage for local migration fingerprints."""

from __future__ import annotations

import pytest

from tests.unit.src.sqlbuild.compiler.planner._helpers.migrations._test_types import (
    MigrationFingerprintTestCase,
    UnparseableFingerprintTestCase,
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
        UnparseableFingerprintTestCase(
            description="unparseable query has no fingerprint",
            query_sql="SELECT FROM WHERE (",
            expected_fingerprint=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unparseable_sql_when_fingerprinting_then_returns_none(
    test_case: UnparseableFingerprintTestCase,
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
