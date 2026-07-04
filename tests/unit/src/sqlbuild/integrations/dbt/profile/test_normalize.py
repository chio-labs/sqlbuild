from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtProfileError
from sqlbuild.integrations.dbt.helpers.profile.normalize import normalize_dbt_profile_connection
from sqlbuild.integrations.dbt.models import (
    NormalizedDbtProfileConnection,
    ResolvedDbtProfileOutput,
)
from tests.unit.src.sqlbuild.integrations.dbt.profile._test_types import (
    DbtProfileNormalizeErrorTestCase,
    DbtProfileNormalizeTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        DbtProfileNormalizeTestCase(
            description="postgres aliases map to psycopg connection config",
            output={
                "type": "postgres",
                "host": "localhost",
                "port": 5432,
                "user": "analytics",
                "pass": "secret",
                "dbname": "warehouse",
                "schema": "analytics",
                "sslmode": "require",
            },
            expected_adapter="postgres",
            expected_connection={
                "host": "localhost",
                "port": 5432,
                "user": "analytics",
                "password": "secret",
                "dbname": "warehouse",
                "sslmode": "require",
            },
            expected_target_schema="analytics",
            expected_target_database=None,
        ),
        DbtProfileNormalizeTestCase(
            description="snowflake preserves connector-compatible credential fields",
            output={
                "type": "snowflake",
                "account": "acct",
                "user": "analytics",
                "password": "secret",
                "warehouse": "transforming",
                "database": "RAW",
                "schema": "ANALYTICS",
                "role": "TRANSFORMER",
                "client_request_mfa_token": True,
                "client_store_temporary_credential": True,
                "custom_connector_option": "preserved",
                "threads": 4,
            },
            expected_adapter="snowflake",
            expected_connection={
                "account": "acct",
                "user": "analytics",
                "password": "secret",
                "warehouse": "transforming",
                "database": "RAW",
                "schema": "ANALYTICS",
                "role": "TRANSFORMER",
                "client_request_mfa_token": True,
                "client_store_temporary_credential": True,
                "custom_connector_option": "preserved",
            },
            expected_target_schema="ANALYTICS",
            expected_target_database="RAW",
        ),
        DbtProfileNormalizeTestCase(
            description="bigquery service account file maps keyfile to credentials_path",
            output={
                "type": "bigquery",
                "method": "service-account",
                "project": "analytics-project",
                "dataset": "marts",
                "keyfile": "/tmp/key.json",
                "location": "US",
            },
            expected_adapter="bigquery",
            expected_connection={
                "project": "analytics-project",
                "credentials_path": "/tmp/key.json",
                "location": "US",
            },
            expected_target_schema="marts",
            expected_target_database="analytics-project",
        ),
        DbtProfileNormalizeTestCase(
            description="databricks pat profile maps host and catalog aliases",
            output={
                "type": "databricks",
                "host": "adb.example.azuredatabricks.net",
                "http_path": "/sql/1.0/warehouses/abc",
                "token": "secret",
                "database": "main",
                "schema": "analytics",
            },
            expected_adapter="databricks",
            expected_connection={
                "server_hostname": "adb.example.azuredatabricks.net",
                "http_path": "/sql/1.0/warehouses/abc",
                "token": "secret",
                "catalog": "main",
                "schema": "analytics",
            },
            expected_target_schema="analytics",
            expected_target_database="main",
        ),
        DbtProfileNormalizeTestCase(
            description="sqlserver sql auth aliases map to pymssql config",
            output={
                "type": "sqlserver",
                "server": "localhost",
                "port": 1433,
                "UID": "sa",
                "PWD": "secret",
                "database": "warehouse",
                "schema": "dbo",
                "authentication": "sql",
            },
            expected_adapter="sqlserver",
            expected_connection={
                "host": "localhost",
                "port": 1433,
                "user": "sa",
                "password": "secret",
                "database": "warehouse",
            },
            expected_target_schema="dbo",
            expected_target_database=None,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_rendered_dbt_profile_when_normalizing_then_returns_sqlbuild_connection(
    test_case: DbtProfileNormalizeTestCase,
    tmp_path: Path,
) -> None:
    resolved: ResolvedDbtProfileOutput = ResolvedDbtProfileOutput(
        project_dir=tmp_path / "dbt_project",
        profiles_dir=tmp_path / "profiles",
        profile_name="analytics",
        target_name="dev",
        output=test_case.output,
    )

    normalized: NormalizedDbtProfileConnection = normalize_dbt_profile_connection(resolved=resolved)

    assert normalized.adapter == test_case.expected_adapter
    assert normalized.connection == test_case.expected_connection
    assert normalized.target_schema == test_case.expected_target_schema
    assert normalized.target_database == test_case.expected_target_database


@pytest.mark.parametrize(
    "test_case",
    (
        DbtProfileNormalizeErrorTestCase(
            description="bigquery service account json is rejected",
            output={
                "type": "bigquery",
                "method": "service-account-json",
                "project": "analytics-project",
                "dataset": "marts",
                "keyfile_json": {"client_email": "svc@example.com"},
            },
            expected_error_fragment="service-account-json",
        ),
        DbtProfileNormalizeErrorTestCase(
            description="databricks oauth is rejected",
            output={
                "type": "databricks",
                "host": "adb.example.azuredatabricks.net",
                "http_path": "/sql/1.0/warehouses/abc",
                "auth_type": "oauth",
                "client_id": "client",
                "client_secret": "secret",
            },
            expected_error_fragment="oauth",
        ),
        DbtProfileNormalizeErrorTestCase(
            description="sqlserver windows auth is rejected",
            output={
                "type": "sqlserver",
                "host": "localhost",
                "database": "warehouse",
                "schema": "dbo",
                "windows_login": True,
            },
            expected_error_fragment="Windows authentication",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unsupported_dbt_profile_auth_when_normalizing_then_raises_clear_error(
    test_case: DbtProfileNormalizeErrorTestCase,
    tmp_path: Path,
) -> None:
    resolved: ResolvedDbtProfileOutput = ResolvedDbtProfileOutput(
        project_dir=tmp_path / "dbt_project",
        profiles_dir=tmp_path / "profiles",
        profile_name="analytics",
        target_name="dev",
        output=test_case.output,
    )

    with pytest.raises(DbtProfileError, match=test_case.expected_error_fragment):
        normalize_dbt_profile_connection(resolved=resolved)
