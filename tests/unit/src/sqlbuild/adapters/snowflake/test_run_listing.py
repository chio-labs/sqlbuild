import pytest

from tests.unit.src.sqlbuild.adapters.snowflake._test_types import SnowflakeRunListingTestCase
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    relation_existence,
    retention_relation,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRunListingTestCase(
            description="unquoted, case-sensitive and wildcard-like names",
            relations=(
                retention_relation("MART", "ORDERS", retention=1),
                retention_relation("MART", "Orders_Mixed", retention=1),
                retention_relation("MART", "ORDERSXLINES", retention=1),
                retention_relation("MART", "CUSTOMERS", retention=1, table_type="VIEW"),
            ),
            lookups=(
                "orders",
                "orders_mixed",
                "Orders_Mixed",
                "orders_lines",
                "customers",
                "products",
            ),
            expected_listings=(0, 2),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_listing_when_checking_existence_then_answers_match_single_lookups(
    test_case: SnowflakeRunListingTestCase,
) -> None:
    single, single_listings = relation_existence(
        relations=test_case.relations, lookups=test_case.lookups, in_build=False
    )
    listed, build_listings = relation_existence(
        relations=test_case.relations, lookups=test_case.lookups, in_build=True
    )

    assert listed == single
    assert (single_listings, build_listings) == test_case.expected_listings
