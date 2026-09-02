from __future__ import annotations

from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.databricks.classes.databricks_adapter import DatabricksAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.adapters.motherduck.classes.motherduck_adapter import MotherDuckAdapter
from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.adapters.sqlserver.classes.sqlserver_adapter import SqlServerAdapter
from tests.unit.src.sqlbuild.adapters._test_types import (
    AdapterManagedWriteSchemaCapabilityTestCase,
)


class _CustomAdapter(BaseAdapter):
    adapter_name: ClassVar[str] = "custom"

    def connect(self, config: dict[str, Any]) -> Any:
        del config
        return None

    def close(self, connection: Any) -> None:
        del connection

    def _execute(self, *, connection: Any, sql: str) -> Any:
        del connection, sql
        return None


@pytest.mark.parametrize(
    "test_case",
    (
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="DuckDB permits its implicit main schema",
            adapter=DuckDbAdapter(),
            expected_allows_implicit_schema=True,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="MotherDuck requires an explicit schema",
            adapter=MotherDuckAdapter(),
            expected_allows_implicit_schema=False,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="Snowflake requires an explicit schema",
            adapter=SnowflakeAdapter(),
            expected_allows_implicit_schema=False,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="BigQuery requires an explicit schema",
            adapter=BigQueryAdapter(),
            expected_allows_implicit_schema=False,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="Databricks requires an explicit schema",
            adapter=DatabricksAdapter(),
            expected_allows_implicit_schema=False,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="Postgres requires an explicit schema despite public default",
            adapter=PostgresAdapter(),
            expected_allows_implicit_schema=False,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="SQL Server requires an explicit schema despite dbo default",
            adapter=SqlServerAdapter(),
            expected_allows_implicit_schema=False,
        ),
        AdapterManagedWriteSchemaCapabilityTestCase(
            description="custom adapters inherit the conservative default",
            adapter=_CustomAdapter(),
            expected_allows_implicit_schema=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_adapter_when_checking_managed_write_schema_capability_then_policy_is_conservative(
    test_case: AdapterManagedWriteSchemaCapabilityTestCase,
) -> None:
    assert (
        test_case.adapter.allows_implicit_managed_write_schema
        is test_case.expected_allows_implicit_schema
    )
