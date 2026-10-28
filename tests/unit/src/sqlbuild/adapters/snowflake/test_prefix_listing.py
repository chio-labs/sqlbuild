import pytest

from sqlbuild.adapter.contract.models import RelationInfo
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakePrefixListingTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    prefix_listing_statements,
    retention_relation,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    OfflineSnowflakeAdapter,
    RecordingSnowflakeWarehouse,
)

_LISTING: tuple[str, ...] = ("SHOW TERSE OBJECTS LIKE '__SQB_AB12__%'",)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakePrefixListingTestCase(
            description="tables and views under the prefix, in one SHOW TERSE OBJECTS",
            relations=(
                retention_relation("TESTS", "__SQB_AB12__SOURCE__ORDERS", retention=1),
                retention_relation(
                    "TESTS", "__SQB_AB12__MODEL__ORDER_TOTALS", retention=1, table_type="VIEW"
                ),
                retention_relation("TESTS", "__SQB_CD34__SOURCE__ORDERS", retention=1),
                retention_relation("TESTS", "ORDERS", retention=1),
            ),
            schema="tests",
            prefix="__sqb_ab12__",
            expected_relations=(
                ("__sqb_ab12__model__order_totals", "view"),
                ("__sqb_ab12__source__orders", "base table"),
            ),
            expected_statements=_LISTING,
        ),
        SnowflakePrefixListingTestCase(
            description="a name LIKE matches only through its underscores is left out",
            relations=(
                retention_relation("TESTS", "__SQB_AB12__SOURCE__ORDERS", retention=1),
                retention_relation("TESTS", "X_SQB_AB12__ORDERS", retention=1),
            ),
            schema="tests",
            prefix="__sqb_ab12__",
            expected_relations=(("__sqb_ab12__source__orders", "base table"),),
            expected_statements=_LISTING,
        ),
        SnowflakePrefixListingTestCase(
            description="a schema that does not exist lists nothing",
            relations=(retention_relation("TESTS", "__SQB_AB12__SOURCE__ORDERS", retention=1),),
            schema="missing",
            prefix="__sqb_ab12__",
            expected_relations=(),
            expected_statements=_LISTING,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_scenario_namespace_when_listing_by_prefix_then_one_show_finds_its_relations(
    test_case: SnowflakePrefixListingTestCase,
) -> None:
    warehouse: RecordingSnowflakeWarehouse = RecordingSnowflakeWarehouse(
        relations=test_case.relations
    )
    adapter: OfflineSnowflakeAdapter = OfflineSnowflakeAdapter(warehouse=warehouse)

    relations: tuple[RelationInfo, ...] | None = adapter.list_relations_with_prefix(
        connection=adapter.connect({}),
        database="analytics",
        schemas=(test_case.schema,),
        prefix=test_case.prefix,
    )

    assert tuple(
        sorted((relation.name, relation.relation_type) for relation in relations or ())
    ) == (test_case.expected_relations)
    assert prefix_listing_statements(warehouse) == test_case.expected_statements
