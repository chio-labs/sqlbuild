"""Unit tests for ingestr integration-loader command construction."""

from __future__ import annotations

import pytest

from sqlbuild.integrations.ingestr.helpers.command import build_ingestr_command
from sqlbuild.integrations.ingestr.models import IngestrSourceConfig
from sqlbuild.spec.models.source import IntegrationLoaderConfig, SourceEntry
from tests.unit.src.sqlbuild.integrations.ingestr._test_types import IngestrCommandTestCase


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
        destination_table="raw.orders",
        vars={"token": "secret"},
        environment="dev",
        run_id="run-1",
        is_reload=True,
    )

    assert command == test_case.expected_command
