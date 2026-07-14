from __future__ import annotations

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import (
    AdapterCloneModeTestCase,
    AdapterDurableCloneTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
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
            description="bigquery durable clone uses table clone",
            adapter=BigQueryAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            expected_statements=("CREATE TABLE `dev.fact_orders` CLONE `prod.fact_orders`",),
            expected_supports_durable_clone=True,
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
    ),
    ids=lambda case: case.description,
)
def test_given_first_party_adapter_when_rendering_durable_clone_then_returns_expected_sql(
    test_case: AdapterDurableCloneTestCase,
) -> None:
    statements: tuple[str, ...] = test_case.adapter.render_durable_clone(
        origin=test_case.source,
        destination=test_case.target,
    )

    assert test_case.adapter.supports_durable_clone() is test_case.expected_supports_durable_clone
    assert statements == test_case.expected_statements


@pytest.mark.parametrize(
    "test_case",
    (
        AdapterCloneModeTestCase(
            description="databricks cheap clone uses shallow clone",
            adapter=DatabricksAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            expected_statements=("CREATE TABLE dev.fact_orders SHALLOW CLONE prod.fact_orders",),
        ),
        AdapterCloneModeTestCase(
            description="databricks hard copy clone uses CTAS fallback",
            adapter=DatabricksAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=True,
            expected_statements=(
                "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        ),
        AdapterCloneModeTestCase(
            description="snowflake cheap clone uses clone",
            adapter=SnowflakeAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            expected_statements=("CREATE OR REPLACE TABLE dev.fact_orders CLONE prod.fact_orders",),
        ),
        AdapterCloneModeTestCase(
            description="snowflake hard copy clone uses transient CTAS fallback",
            adapter=SnowflakeAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=True,
            expected_statements=(
                "CREATE OR REPLACE TRANSIENT TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        ),
        AdapterCloneModeTestCase(
            description="bigquery cheap clone uses clone",
            adapter=BigQueryAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            expected_statements=("CREATE TABLE `dev.fact_orders` CLONE `prod.fact_orders`",),
        ),
        AdapterCloneModeTestCase(
            description="bigquery hard copy clone uses CTAS fallback",
            adapter=BigQueryAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=True,
            expected_statements=(
                "CREATE OR REPLACE TABLE `dev.fact_orders` AS SELECT * FROM prod.fact_orders",
            ),
        ),
        AdapterCloneModeTestCase(
            description="postgres clone always uses CTAS fallback",
            adapter=PostgresAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            expected_statements=(
                "DROP TABLE IF EXISTS dev.fact_orders",
                "CREATE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        ),
        AdapterCloneModeTestCase(
            description="sqlserver clone always uses select into fallback",
            adapter=SqlServerAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            expected_statements=(
                "DROP TABLE IF EXISTS dev.fact_orders",
                "SELECT * INTO dev.fact_orders FROM "
                "(SELECT * FROM prod.fact_orders) AS __create_source",
            ),
        ),
        AdapterCloneModeTestCase(
            description="duckdb clone always uses CTAS fallback",
            adapter=DuckDbAdapter(),
            source="prod.fact_orders",
            target="dev.fact_orders",
            hard_copy=False,
            expected_statements=(
                "CREATE OR REPLACE TABLE dev.fact_orders AS SELECT * FROM prod.fact_orders",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_first_party_adapter_when_rendering_clone_mode_then_returns_expected_sql(
    test_case: AdapterCloneModeTestCase,
) -> None:
    statements: tuple[str, ...] = test_case.adapter.render_clone(
        origin=test_case.source,
        destination=test_case.target,
        hard_copy=test_case.hard_copy,
    )

    assert statements == test_case.expected_statements
