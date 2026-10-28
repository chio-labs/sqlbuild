import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapter.contract.models import (
    RenderedRetentionChange,
    RetentionRequest,
    RetentionState,
)
from sqlbuild.adapter.contract.types import RetentionChangePhase
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeBatchedRetentionErrorTestCase,
    SnowflakeBatchedRetentionTestCase,
    SnowflakeRetentionTestCase,
    SnowflakeShowRetentionTestCase,
)
from tests.unit.src.sqlbuild.adapters.snowflake.helpers import (
    retention_relation,
    retention_request,
    run_metadata_steps,
    show_statement,
)
from tests.unit.src.sqlbuild.adapters.snowflake.inspection.helpers import (
    OfflineSnowflakeAdapter,
    RecordingSnowflakeWarehouse,
)

_MART_LISTING: tuple[str, ...] = (
    'SHOW TABLES IN SCHEMA "ANALYTICS"."MART"',
    'SHOW VIEWS IN SCHEMA "ANALYTICS"."MART"',
)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeRetentionTestCase(
            description="transient table retention is inspected and altered without conversion",
            desired_days=7,
            relation=retention_relation("MART", "RESULTS", retention=3, transient=True),
            expected_days=3,
            expected_kind="TRANSIENT",
            expected_sql="ALTER TABLE analytics.mart.results SET DATA_RETENTION_TIME_IN_DAYS = 7",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_relation_when_managing_retention_then_observes_and_renders_alter(
    test_case: SnowflakeRetentionTestCase,
) -> None:
    adapter: OfflineSnowflakeAdapter = OfflineSnowflakeAdapter(
        warehouse=RecordingSnowflakeWarehouse(relations=(test_case.relation,))
    )
    request: RetentionRequest = retention_request(
        schema="mart", name="results", desired_days=test_case.desired_days
    )

    state: RetentionState = adapter.inspect_retention(
        connection=adapter.connect({}), request=request
    )
    changes: tuple[RenderedRetentionChange, ...] = adapter.render_retention_changes(request=request)

    assert state.effective_days == test_case.expected_days
    assert state.relation_kind == test_case.expected_kind
    assert state.is_transient is True
    assert changes[0].phase == RetentionChangePhase.ALTER
    assert changes[0].statements == (test_case.expected_sql,)


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeShowRetentionTestCase(
            description="one table outside a build is read alone, without a warehouse",
            relations=(retention_relation("MART", "RESULTS", retention=3, transient=True),),
            steps=(("retention", "mart", "results"),),
            in_build=False,
            expected_steps=((3, ("SHOW TABLES LIKE 'RESULTS'",)),),
        ),
        SnowflakeShowRetentionTestCase(
            description="a lowercase name finds its stored table, not a LIKE-wildcard sibling",
            relations=(
                retention_relation("MART", "ORDERSXLINES", retention=5),
                retention_relation("MART", "ORDERS_LINES", retention=2),
            ),
            steps=(("retention", "mart", "orders_lines"),),
            in_build=False,
            expected_steps=((2, ("SHOW TABLES LIKE 'ORDERS_LINES'",)),),
        ),
        SnowflakeShowRetentionTestCase(
            description="a build answers retention from the listing its existence checks made",
            relations=(
                retention_relation("MART", "ORDERS", retention=7),
                retention_relation("MART", "CUSTOMERS", retention=1),
                retention_relation("MART", "PRODUCTS", retention=0, transient=True),
            ),
            steps=(
                ("exists", "mart", "orders"),
                ("exists", "mart", "customers"),
                ("retention", "mart", "products"),
                ("retention", "mart", "orders"),
            ),
            in_build=True,
            expected_steps=(
                (None, ("SHOW TERSE TABLES LIKE 'ORDERS'",)),
                (None, _MART_LISTING),
                (0, ()),
                (7, ()),
            ),
        ),
        SnowflakeShowRetentionTestCase(
            description="a table the build replaced after the listing is read again alone",
            relations=(
                retention_relation("MART", "ORDERS", retention=7),
                retention_relation("MART", "CUSTOMERS", retention=1),
            ),
            steps=(
                ("exists", "mart", "orders"),
                ("exists", "mart", "customers"),
                ("replace", "mart", "orders"),
                ("retention", "mart", "customers"),
                ("retention", "mart", "orders"),
            ),
            in_build=True,
            expected_steps=(
                (None, ("SHOW TERSE TABLES LIKE 'ORDERS'",)),
                (None, _MART_LISTING),
                (None, ("CREATE OR REPLACE TABLE analytics.mart.orders (id INT)",)),
                (1, ()),
                (7, ("SHOW TABLES LIKE 'ORDERS'",)),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_relations_when_inspecting_retention_then_show_tables_answers_each_lookup(
    test_case: SnowflakeShowRetentionTestCase,
) -> None:
    steps: tuple[tuple[int | None, tuple[str, ...]], ...] = run_metadata_steps(
        relations=test_case.relations, steps=test_case.steps, in_build=test_case.in_build
    )

    assert steps == test_case.expected_steps


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBatchedRetentionTestCase(
            description="three tables in two schemas list a schema once or read one table alone",
            requests=(("mart", "orders"), ("mart", "customers"), ("staging", "stg_orders")),
            relations=(
                retention_relation("MART", "ORDERS", retention=7),
                retention_relation("MART", "CUSTOMERS", retention=1),
                retention_relation("STAGING", "STG_ORDERS", retention=0, transient=True),
            ),
            expected_queries=(*_MART_LISTING, "SHOW TABLES LIKE 'STG_ORDERS'"),
            expected_days={"orders": 7, "customers": 1, "stg_orders": 0},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_many_relations_when_inspecting_retention_then_queries_once_per_schema(
    test_case: SnowflakeBatchedRetentionTestCase,
) -> None:
    warehouse: RecordingSnowflakeWarehouse = RecordingSnowflakeWarehouse(
        relations=test_case.relations
    )
    adapter: OfflineSnowflakeAdapter = OfflineSnowflakeAdapter(warehouse=warehouse)
    requests: tuple[RetentionRequest, ...] = tuple(
        retention_request(schema=schema, name=name) for schema, name in test_case.requests
    )

    states: dict[str, RetentionState] = adapter.inspect_retentions(
        connection=adapter.connect({}), requests=requests
    )

    assert tuple(show_statement(query.sql) for query in warehouse.queries) == (
        test_case.expected_queries
    )
    assert {request_id: state.effective_days for request_id, state in states.items()} == (
        test_case.expected_days
    )


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeBatchedRetentionErrorTestCase(
            description="a table missing from metadata fails like single inspection",
            requests=(("mart", "orders"), ("mart", "customers")),
            relations=(retention_relation("MART", "ORDERS", retention=7),),
            expected_error="Snowflake retention metadata not found for customers",
        ),
        SnowflakeBatchedRetentionErrorTestCase(
            description="a view in place of the table has no retention to manage",
            requests=(("mart", "orders"),),
            relations=(retention_relation("MART", "ORDERS", retention=7, table_type="VIEW"),),
            expected_error="Snowflake retention metadata not found for orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_relation_when_batch_inspecting_retention_then_raises(
    test_case: SnowflakeBatchedRetentionErrorTestCase,
) -> None:
    adapter: OfflineSnowflakeAdapter = OfflineSnowflakeAdapter(
        warehouse=RecordingSnowflakeWarehouse(relations=test_case.relations)
    )
    requests: tuple[RetentionRequest, ...] = tuple(
        retention_request(schema=schema, name=name) for schema, name in test_case.requests
    )

    with pytest.raises(AdapterUserError, match=test_case.expected_error):
        _ = adapter.inspect_retentions(connection=adapter.connect({}), requests=requests)
