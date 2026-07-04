"""Unit tests for dlt destination mapping."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.integrations.dlt.constants import DLT_DESTINATION_ADAPTERS
from sqlbuild.integrations.dlt.exceptions import DltIntegrationError
from sqlbuild.integrations.dlt.helpers.destination import build_dlt_destination
from sqlbuild.integrations.dlt.models import DltDestinationConfig
from tests.unit.src.sqlbuild.integrations.dlt._test_types import (
    DltDestinationCoverageTestCase,
    DltDestinationErrorTestCase,
    DltDestinationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DltDestinationTestCase(
            description="maps duckdb destination",
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            dataset_name="raw",
            expected_destination_name="duckdb",
            expected_dataset_name="raw",
            expected_caps_params={"naming_convention": "sql_ci_v1"},
        ),
        DltDestinationTestCase(
            description="defaults duckdb dataset to main",
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            dataset_name=None,
            expected_destination_name="duckdb",
            expected_dataset_name="main",
            expected_caps_params={"naming_convention": "sql_ci_v1"},
        ),
        DltDestinationTestCase(
            description="allows destination overrides",
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            dataset_name="raw",
            destination_config={"naming_convention": "sql_cs_v1", "create_indexes": True},
            expected_destination_name="duckdb",
            expected_dataset_name="raw",
            expected_config_params={"create_indexes": True},
            expected_caps_params={"naming_convention": "sql_cs_v1"},
        ),
        DltDestinationTestCase(
            description="maps motherduck destination",
            adapter_name="motherduck",
            connection_config={"database": "analytics", "token": "token"},
            dataset_name="raw",
            expected_destination_name="motherduck",
            expected_dataset_name="raw",
        ),
        DltDestinationTestCase(
            description="maps snowflake destination",
            adapter_name="snowflake",
            connection_config={
                "account": "acct",
                "user": "user",
                "password": "pass",
                "warehouse": "wh",
                "database": "db",
            },
            dataset_name="raw",
            expected_destination_name="snowflake",
            expected_dataset_name="raw",
        ),
        DltDestinationTestCase(
            description="maps bigquery destination",
            adapter_name="bigquery",
            connection_config={"project": "proj", "location": "US"},
            dataset_name="raw",
            expected_destination_name="bigquery",
            expected_dataset_name="raw",
        ),
        DltDestinationTestCase(
            description="maps databricks destination",
            adapter_name="databricks",
            connection_config={
                "server_hostname": "dbc.example.com",
                "http_path": "/sql/1.0/warehouses/abc",
                "token": "token",
                "catalog": "main",
            },
            dataset_name="raw",
            expected_destination_name="databricks",
            expected_dataset_name="raw",
        ),
        DltDestinationTestCase(
            description="maps postgres destination",
            adapter_name="postgres",
            connection_config={
                "host": "localhost",
                "dbname": "db",
                "user": "user",
                "password": "pass",
            },
            dataset_name="raw",
            expected_destination_name="postgres",
            expected_dataset_name="raw",
        ),
        DltDestinationTestCase(
            description="maps sqlserver destination",
            adapter_name="sqlserver",
            connection_config={
                "host": "localhost",
                "database": "db",
                "user": "sa",
                "password": "pass",
            },
            dataset_name="raw",
            expected_destination_name="mssql",
            expected_dataset_name="raw",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sqlbuild_connection_when_building_dlt_destination_then_maps_destination(
    test_case: DltDestinationTestCase,
) -> None:
    result: DltDestinationConfig = build_dlt_destination(
        adapter_name=test_case.adapter_name,
        connection_config=test_case.connection_config,
        destination_config=test_case.destination_config,
        dataset_name=test_case.dataset_name,
    )

    assert result.destination.destination_name == test_case.expected_destination_name
    assert result.dataset_name == test_case.expected_dataset_name
    expected_key: str
    for expected_key, expected_value in test_case.expected_config_params.items():
        assert result.destination.config_params[expected_key] == expected_value
    for expected_key, expected_value in test_case.expected_caps_params.items():
        assert result.destination.caps_params[expected_key] == expected_value


@pytest.mark.parametrize(
    "test_case",
    [
        DltDestinationErrorTestCase(
            description="requires schema for real warehouse",
            adapter_name="postgres",
            connection_config={"host": "localhost", "dbname": "db", "user": "user"},
            dataset_name=None,
            expected_error_fragment="requires an explicit dlt source schema",
        ),
        DltDestinationErrorTestCase(
            description="rejects sqlbuild owned destination keys",
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            dataset_name="raw",
            destination_config={"credentials": "other.duckdb"},
            expected_error_fragment="cannot define SQLBuild-owned key",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_real_warehouse_without_schema_when_building_dlt_destination_then_raises(
    test_case: DltDestinationErrorTestCase,
) -> None:
    with pytest.raises(DltIntegrationError) as exc_info:
        build_dlt_destination(
            adapter_name=test_case.adapter_name,
            connection_config=test_case.connection_config,
            destination_config=test_case.destination_config,
            dataset_name=test_case.dataset_name,
        )

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        DltDestinationCoverageTestCase(
            description="covers all builtin adapters",
            expected_adapters=frozenset(BuiltinAdapter),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_builtin_adapters_when_checking_dlt_destination_support_then_all_are_explicit(
    test_case: DltDestinationCoverageTestCase,
) -> None:
    assert DLT_DESTINATION_ADAPTERS == test_case.expected_adapters
