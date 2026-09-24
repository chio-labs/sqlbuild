"""Unit coverage for the single-statement migration clone capability."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.contract.exceptions import AdapterUserError
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import AdapterReplaceWithCloneTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterReplaceWithCloneTestCase(
            description="snowflake replaces with a zero-copy clone",
            adapter=SnowflakeAdapter(),
            origin_is_transient=False,
            expected_statement="CREATE OR REPLACE TABLE dev.stg_customer_orders CLONE dev.stg_orders",
        ),
        AdapterReplaceWithCloneTestCase(
            description="snowflake preserves a transient origin table type",
            adapter=SnowflakeAdapter(),
            origin_is_transient=True,
            expected_statement=(
                "CREATE OR REPLACE TRANSIENT TABLE dev.stg_customer_orders CLONE dev.stg_orders"
            ),
        ),
        AdapterReplaceWithCloneTestCase(
            description="databricks uses an independent deep clone",
            adapter=DatabricksAdapter(),
            origin_is_transient=False,
            expected_statement=(
                "CREATE OR REPLACE TABLE dev.stg_customer_orders DEEP CLONE dev.stg_orders"
            ),
        ),
        AdapterReplaceWithCloneTestCase(
            description="bigquery replaces with a table clone",
            adapter=BigQueryAdapter(),
            origin_is_transient=False,
            expected_statement=(
                "CREATE OR REPLACE TABLE `dev.stg_customer_orders` CLONE `dev.stg_orders`"
            ),
        ),
        AdapterReplaceWithCloneTestCase(
            description="duckdb copies with one replacing CTAS",
            adapter=DuckDbAdapter(),
            origin_is_transient=False,
            expected_statement=(
                "CREATE OR REPLACE TABLE dev.stg_customer_orders AS SELECT * FROM dev.stg_orders"
            ),
        ),
        AdapterReplaceWithCloneTestCase(
            description="motherduck inherits the replacing CTAS",
            adapter=MotherDuckAdapter(),
            origin_is_transient=False,
            expected_statement=(
                "CREATE OR REPLACE TABLE dev.stg_customer_orders AS SELECT * FROM dev.stg_orders"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_adapter_when_rendering_replace_with_clone_then_returns_one_statement(
    test_case: AdapterReplaceWithCloneTestCase,
) -> None:
    statement: str = test_case.adapter.render_replace_with_clone(
        origin="dev.stg_orders",
        destination="dev.stg_customer_orders",
        origin_is_transient=test_case.origin_is_transient,
    )

    assert statement == test_case.expected_statement


@pytest.mark.parametrize(
    "test_case",
    [
        AdapterReplaceWithCloneTestCase(
            description="postgres rejects model migrations",
            adapter=PostgresAdapter(),
            origin_is_transient=False,
            expected_statement=None,
            expected_error_fragment="does not support model migrations",
        ),
        AdapterReplaceWithCloneTestCase(
            description="sqlserver rejects model migrations",
            adapter=SqlServerAdapter(),
            origin_is_transient=False,
            expected_statement=None,
            expected_error_fragment="does not support model migrations",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_adapter_when_rendering_replace_with_clone_then_raises(
    test_case: AdapterReplaceWithCloneTestCase,
) -> None:
    with pytest.raises(AdapterUserError, match=test_case.expected_error_fragment):
        _ = test_case.adapter.render_replace_with_clone(
            origin="dev.stg_orders", destination="dev.stg_customer_orders"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
