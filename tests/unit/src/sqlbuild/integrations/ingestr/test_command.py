"""Unit tests for ingestr integration-loader command construction."""

from __future__ import annotations

import pytest

from sqlbuild._native import IntegrationLoaderConfig, SourceEntry, build_ingestr_command
from sqlbuild.integrations.ingestr._helpers.command import build_ingestr_command
from sqlbuild.integrations.ingestr.exceptions import IngestrIntegrationError
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.contracts.models import IntegrationLoaderConfig, SourceEntry
from tests.unit.src.sqlbuild.integrations.ingestr._test_types import (
    IngestrCommandErrorTestCase,
    IngestrCommandTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrCommandTestCase(
            description="uses sqlbuild destination and resolved templates",
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            expected_command=(
                "ingestr",
                "ingest",
                "--source-uri",
                "stripe://secret",
                "--source-table",
                "charges",
                "--dest-uri",
                "duckdb:///warehouse.duckdb",
                "--dest-table",
                "raw.orders",
                "--yes",
                "--progress",
                "log",
                "--incremental-strategy",
                "merge",
                "--incremental-key",
                "updated_at",
                "--primary-key",
                "id",
                "--columns",
                "id,updated_at",
                "--full-refresh",
                "--debug",
            ),
        ),
        IngestrCommandTestCase(
            description="supports sqlserver destination uri",
            adapter_name="sqlserver",
            connection_config={
                "host": "localhost",
                "port": 1433,
                "user": "sa",
                "password": "Sqlbuild!2026",
                "database": "analytics",
            },
            expected_command=(
                "ingestr",
                "ingest",
                "--source-uri",
                "stripe://secret",
                "--source-table",
                "charges",
                "--dest-uri",
                "mssql://sa:Sqlbuild%212026@localhost:1433/analytics"
                "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes",
                "--dest-table",
                "raw.orders",
                "--yes",
                "--progress",
                "log",
                "--incremental-strategy",
                "merge",
                "--incremental-key",
                "updated_at",
                "--primary-key",
                "id",
                "--columns",
                "id,updated_at",
                "--full-refresh",
                "--debug",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ingestr_source_when_building_command_then_it_uses_sqlbuild_destination(
    test_case: IngestrCommandTestCase,
) -> None:
    source_entry: SourceEntry = SourceEntry(
        name="raw_orders",
        schema="raw",
        table="orders",
        integration_loader=IntegrationLoaderConfig(
            kind="ingestr",
            config=IngestrSourceConfig(
                source_uri="stripe://${token}",
                source_table="charges",
                strategy="merge",
                incremental_key="updated_at",
                primary_key=("id",),
                columns="id,updated_at",
                extra_args=("--debug",),
            ),
        ),
    )

    command: tuple[str, ...] = build_ingestr_command(
        source_entry=source_entry,
        adapter_name=test_case.adapter_name,
        connection_config=test_case.connection_config,
        destination_name="orders",
        vars={"token": "secret"},
        environment="dev",
        run_id="run-1",
        is_reload=True,
    )

    assert command == test_case.expected_command


@pytest.mark.parametrize(
    "test_case",
    [
        IngestrCommandErrorTestCase(
            description="unsupported adapter",
            source_entry=SourceEntry(
                name="raw_orders",
                integration_loader=IntegrationLoaderConfig(
                    kind="ingestr",
                    config=IngestrSourceConfig(source_uri="csv://x", source_table="orders"),
                ),
            ),
            adapter_name="fabric",
            connection_config={},
            expected_message="Adapter 'fabric' does not support ingestr integration loaders",
        ),
        IngestrCommandErrorTestCase(
            description="blank required connection setting",
            source_entry=SourceEntry(
                name="raw_orders",
                integration_loader=IntegrationLoaderConfig(
                    kind="ingestr",
                    config=IngestrSourceConfig(source_uri="csv://x", source_table="orders"),
                ),
            ),
            adapter_name="postgres",
            connection_config={"user": "   "},
            expected_message=(
                "Adapter 'postgres' requires connection.user for ingestr integration loaders"
            ),
        ),
        IngestrCommandErrorTestCase(
            description="source without ingestr config",
            source_entry=SourceEntry(name="raw_orders"),
            adapter_name="duckdb",
            connection_config={"database": "warehouse.duckdb"},
            expected_message="Source 'raw_orders' does not define ingestr config",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_unbuildable_ingestr_source_when_building_command_then_raises_integration_error(
    test_case: IngestrCommandErrorTestCase,
) -> None:
    with pytest.raises(IngestrIntegrationError) as raised:
        _ = build_ingestr_command(
            source_entry=test_case.source_entry,
            adapter_name=test_case.adapter_name,
            connection_config=test_case.connection_config,
            destination_name="orders",
            vars={},
            environment=None,
            run_id="run-1",
            is_reload=False,
        )

    assert str(raised.value) == test_case.expected_message
