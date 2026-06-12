"""Integration tests for resolve_model_sql executing resolved SQL against real DuckDB."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledRelationLocation,
)
from sqlbuild.compiler.planner.models import ModelCursorSnapshot, WarehouseSnapshot
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry
from tests.integration.src.sqlbuild.compiler.planner.helpers.resolve._test_types import (
    ResolveAndExecuteTestCase,
    ResolveSourceTestCase,
)
from tests.integration.src.sqlbuild.compiler.planner.helpers.resolve.helpers import (
    _ResolveResult,
    build_model,
    resolve_and_execute,
)

REF_TEST_CASES: list[ResolveAndExecuteTestCase] = [
    ResolveAndExecuteTestCase(
        description="resolves ref to qualified name and returns all rows",
        setup_sql=(
            "CREATE TABLE staging.raw_orders (order_id INTEGER, status VARCHAR)",
            "INSERT INTO staging.raw_orders VALUES (1, 'paid'), (2, 'shipped'), (3, 'cancelled')",
        ),
        query_sql='SELECT order_id, status FROM __ref("raw_orders")',
        model_config={"materialized": "table", "schema": "staging"},
        ref_names=("raw_orders",),
        expected_row_count=3,
        expected_column_types={"order_id": "INTEGER", "status": "VARCHAR"},
    ),
    ResolveAndExecuteTestCase(
        description="resolves multiple refs in a join and returns matched rows",
        setup_sql=(
            "CREATE TABLE staging.orders (order_id INTEGER, customer_id INTEGER)",
            "INSERT INTO staging.orders VALUES (1, 10), (2, 20)",
            "CREATE TABLE staging.customers (customer_id INTEGER, name VARCHAR)",
            "INSERT INTO staging.customers VALUES (10, 'alice'), (20, 'bob'), (30, 'charlie')",
        ),
        query_sql=(
            'SELECT o.order_id, c.name FROM __ref("orders") o '
            'JOIN __ref("customers") c ON o.customer_id = c.customer_id'
        ),
        model_config={"materialized": "table", "schema": "staging"},
        ref_names=("orders", "customers"),
        expected_row_count=2,
        expected_column_types={"order_id": "INTEGER", "name": "VARCHAR"},
    ),
]

SOURCE_TEST_CASES: list[ResolveSourceTestCase] = [
    ResolveSourceTestCase(
        description="resolves source with type enforcement CAST producing enforced column types",
        setup_sql=(
            "CREATE TABLE raw.payments (payment_id INTEGER, amount VARCHAR, note VARCHAR)",
            "INSERT INTO raw.payments VALUES (1, '99.50', 'tip'), (2, '200.00', 'refund')",
        ),
        query_sql='SELECT payment_id, amount, note FROM __source("raw_payments")',
        model_config={"materialized": "table", "schema": "staging"},
        source_map={
            "raw_payments": SourceEntry(
                name="raw_payments",
                schema="raw",
                table="payments",
                type_enforcement=True,
                columns=(
                    SourceColumnEntry(name="payment_id", type="BIGINT"),
                    SourceColumnEntry(name="amount", type="DECIMAL"),
                ),
            ),
        },
        source_warehouse_columns={
            "raw_payments": (
                ColumnInfo(name="payment_id", type="INTEGER"),
                ColumnInfo(name="amount", type="VARCHAR"),
                ColumnInfo(name="note", type="VARCHAR"),
            ),
        },
        expected_row_count=2,
        expected_column_types={
            "payment_id": "BIGINT",
            "amount": "DECIMAL(18,3)",
            "note": "VARCHAR",
        },
    ),
    ResolveSourceTestCase(
        description="resolves source without enforcement preserving original column types",
        setup_sql=(
            "CREATE TABLE raw.events (event_id INTEGER, payload VARCHAR)",
            "INSERT INTO raw.events VALUES (1, 'click'), (2, 'view')",
        ),
        query_sql='SELECT event_id, payload FROM __source("raw_events")',
        model_config={"materialized": "table", "schema": "staging"},
        source_map={
            "raw_events": SourceEntry(
                name="raw_events",
                schema="raw",
                table="events",
            ),
        },
        source_warehouse_columns={},
        expected_row_count=2,
        expected_column_types={"event_id": "INTEGER", "payload": "VARCHAR"},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    REF_TEST_CASES,
    ids=[case.description for case in REF_TEST_CASES],
)
def test_given_refs_when_resolving_and_executing_then_returns_expected_rows(
    test_case: ResolveAndExecuteTestCase,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    model: CompiledModel = build_model(
        name="test_model",
        query_sql=test_case.query_sql,
        config=test_case.model_config,
        ref_names=test_case.ref_names,
    )
    model_locations: dict[str, CompiledRelationLocation] = {
        ref_name: CompiledRelationLocation(
            database=None,
            schema="staging",
            name=ref_name,
            qualified_name=f"staging.{ref_name}",
        )
        for ref_name in test_case.ref_names
    }

    result: _ResolveResult = resolve_and_execute(
        model=model,
        snapshot=WarehouseSnapshot(),
        model_locations=model_locations,
        source_map={},
        source_warehouse_columns={},
        connection=connection,
    )

    assert len(result.rows) == test_case.expected_row_count
    col_name: str
    expected_type: str
    for col_name, expected_type in test_case.expected_column_types.items():
        assert result.column_types[col_name] == expected_type


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveAndExecuteTestCase(
            description="resolves incremental source with cursor filter and returns bounded rows",
            setup_sql=(
                "CREATE TABLE staging.raw_events (event_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.raw_events VALUES "
                "(1, '2024-01-01'), (2, '2024-01-15'), (3, '2024-02-01'), (4, '2024-03-01')",
                "CREATE TABLE staging.fact_events (event_id INTEGER, event_time TIMESTAMP)",
                "INSERT INTO staging.fact_events VALUES (1, '2024-01-15')",
            ),
            query_sql='SELECT event_id, event_time FROM __source("raw_events")',
            model_config={
                "materialized": "incremental",
                "incremental_strategy": "delete_insert",
                "cursor": "event_time",
                "cursor_inputs": {"raw_events": "event_time"},
                "schema": "staging",
            },
            ref_names=(),
            expected_row_count=2,
            expected_column_types={"event_id": "INTEGER", "event_time": "TIMESTAMP"},
        ),
    ],
    ids=["resolves incremental source with cursor filter and returns bounded rows"],
)
def test_given_incremental_source_when_resolving_and_executing_then_returns_cursor_bounded_rows(
    test_case: ResolveAndExecuteTestCase,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    model: CompiledModel = build_model(
        name="fact_events",
        query_sql=test_case.query_sql,
        config=test_case.model_config,
        ref_names=test_case.ref_names,
    )
    snapshot: WarehouseSnapshot = WarehouseSnapshot(
        cursor_snapshots={
            "fact_events": ModelCursorSnapshot(
                target_max="2024-01-15 00:00:00",
                upstream_mins=("2024-01-01 00:00:00",),
                upstream_maxes=("2024-03-01 00:00:00",),
            ),
        },
    )

    result: _ResolveResult = resolve_and_execute(
        model=model,
        snapshot=snapshot,
        model_locations={},
        source_map={
            "raw_events": SourceEntry(name="raw_events", schema="staging", table="raw_events")
        },
        source_warehouse_columns={},
        connection=connection,
    )

    assert len(result.rows) == test_case.expected_row_count
    assert "WHERE" in result.resolved_sql
    col_name: str
    expected_type: str
    for col_name, expected_type in test_case.expected_column_types.items():
        assert result.column_types[col_name] == expected_type


@pytest.mark.parametrize(
    "test_case",
    SOURCE_TEST_CASES,
    ids=[case.description for case in SOURCE_TEST_CASES],
)
def test_given_sources_when_resolving_and_executing_then_returns_expected_rows_and_types(
    test_case: ResolveSourceTestCase,
    connection: Any,
) -> None:
    statement: str
    for statement in test_case.setup_sql:
        connection.execute(statement)

    model: CompiledModel = build_model(
        name="test_model",
        query_sql=test_case.query_sql,
        config=test_case.model_config,
        ref_names=(),
    )

    result: _ResolveResult = resolve_and_execute(
        model=model,
        snapshot=WarehouseSnapshot(),
        model_locations={},
        source_map=test_case.source_map,
        source_warehouse_columns=test_case.source_warehouse_columns,
        connection=connection,
    )

    assert len(result.rows) == test_case.expected_row_count
    col_name: str
    expected_type: str
    for col_name, expected_type in test_case.expected_column_types.items():
        assert result.column_types[col_name] == expected_type
