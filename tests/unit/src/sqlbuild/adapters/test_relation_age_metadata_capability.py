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
    AdapterRelationAgeMetadataCapabilityTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="Snowflake reads created and last_altered",
            adapter=SnowflakeAdapter(),
            expected_supported=True,
        ),
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="Databricks reads created and last_altered",
            adapter=DatabricksAdapter(),
            expected_supported=True,
        ),
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="BigQuery reads creation and last-modified times",
            adapter=BigQueryAdapter(),
            expected_supported=True,
        ),
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="SQL Server modify_date ignores data writes",
            adapter=SqlServerAdapter(),
            expected_supported=False,
        ),
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="Postgres catalog has no relation timestamps",
            adapter=PostgresAdapter(),
            expected_supported=False,
        ),
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="DuckDB catalog has no relation timestamps",
            adapter=DuckDbAdapter(),
            expected_supported=False,
        ),
        AdapterRelationAgeMetadataCapabilityTestCase(
            description="MotherDuck catalog has no relation timestamps",
            adapter=MotherDuckAdapter(),
            expected_supported=False,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_adapter_when_checking_relation_age_metadata_then_matches_catalog_reliability(
    test_case: AdapterRelationAgeMetadataCapabilityTestCase,
) -> None:
    assert test_case.adapter.supports_relation_age_metadata() is test_case.expected_supported
