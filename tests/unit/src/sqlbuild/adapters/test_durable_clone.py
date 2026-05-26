from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.client import BigQueryAdapter
from sqlbuild.adapters.databricks.client import DatabricksAdapter
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.adapters.motherduck.client import MotherDuckAdapter
from sqlbuild.adapters.postgres.client import PostgresAdapter
from sqlbuild.adapters.snowflake.client import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.client import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import AdapterDurableCloneTestCase

DURABLE_CLONE_TEST_CASES: tuple[AdapterDurableCloneTestCase, ...] = (
    AdapterDurableCloneTestCase(
        description="duckdb durable clone uses CTAS fallback",
        adapter=DuckDbAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=(
            "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
        ),
        expected_supports_durable_clone=False,
    ),
    AdapterDurableCloneTestCase(
        description="motherduck durable clone inherits CTAS fallback",
        adapter=MotherDuckAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=(
            "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
        ),
        expected_supports_durable_clone=False,
    ),
    AdapterDurableCloneTestCase(
        description="bigquery durable clone uses CTAS fallback",
        adapter=BigQueryAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=(
            "CREATE OR REPLACE TABLE `dev.fact_orders` AS SELECT * FROM prod.fact_orders",
        ),
        expected_supports_durable_clone=False,
    ),
    AdapterDurableCloneTestCase(
        description="postgres durable clone uses drop and CTAS fallback",
        adapter=PostgresAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=(
            "DROP TABLE IF EXISTS dev.fact_orders",
            "CREATE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
        ),
        expected_supports_durable_clone=False,
    ),
    AdapterDurableCloneTestCase(
        description="sqlserver durable clone uses select into fallback",
        adapter=SqlServerAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=(
            "DROP TABLE IF EXISTS dev.fact_orders",
            "SELECT * INTO dev.fact_orders FROM "
            "(SELECT * FROM prod.fact_orders) AS __create_source",
        ),
        expected_supports_durable_clone=False,
    ),
    AdapterDurableCloneTestCase(
        description="snowflake durable clone uses clone",
        adapter=SnowflakeAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=("CREATE OR REPLACE TABLE dev.fact_orders CLONE prod.fact_orders",),
        expected_supports_durable_clone=True,
    ),
    AdapterDurableCloneTestCase(
        description="databricks durable clone uses deep clone",
        adapter=DatabricksAdapter(),
        source="prod.fact_orders",
        target="dev.fact_orders",
        expected_statements=("CREATE TABLE dev.fact_orders DEEP CLONE prod.fact_orders",),
        expected_supports_durable_clone=True,
    ),
)


@pytest.mark.parametrize(
    "test_case",
    DURABLE_CLONE_TEST_CASES,
    ids=[case.description for case in DURABLE_CLONE_TEST_CASES],
)
def test_given_first_party_adapter_when_rendering_durable_clone_then_returns_expected_sql(
    test_case: AdapterDurableCloneTestCase,
) -> None:
    statements: tuple[str, ...] = test_case.adapter.render_durable_clone(
        source=test_case.source,
        target=test_case.target,
    )

    assert test_case.adapter.supports_durable_clone() is test_case.expected_supports_durable_clone
    assert statements == test_case.expected_statements
