"""Snowflake view definitions read one schema at a time through the inspection catalog."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.relations.classes.inspection_catalog import InspectionCatalog
from sqlbuild.adapter.relations.main.open_inspection_catalog import open_inspection_catalog
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from tests.unit.src.sqlbuild.adapters.snowflake._test_types import (
    SnowflakeViewDefinitionsTestCase,
)


class _Rows:
    def __init__(self, rows: list[tuple[str, ...]]) -> None:
        self._rows: list[tuple[str, ...]] = rows

    def fetchall(self) -> list[tuple[str, ...]]:
        return self._rows


class _ViewDefinitionAdapter(SnowflakeAdapter):
    """Answers INFORMATION_SCHEMA.VIEWS reads from stored rows, matching names like Snowflake."""

    def __init__(self, *, stored: tuple[tuple[str, str], ...]) -> None:
        super().__init__()
        self.stored: tuple[tuple[str, str], ...] = stored
        self.queries: list[str] = []

    def execute(self, *, connection: Any, sql: str) -> Any:
        del connection
        self.queries.append(sql)
        if sql.startswith("SELECT TABLE_NAME, VIEW_DEFINITION"):
            return _Rows([row for row in self.stored if f"UPPER('{row[0]}')" in sql.upper()])
        return _Rows(
            [(definition,) for name, definition in self.stored if f"'{name.upper()}'" in sql.upper()]
        )


@pytest.mark.parametrize(
    "test_case",
    (
        SnowflakeViewDefinitionsTestCase(
            description="prefetched views are served without further queries, absent ones as none",
            stored_rows=(("ORDERS_VIEW", "SELECT 1"), ("CUSTOMERS_VIEW", "SELECT 2")),
            prefetched_names=("orders_view", "customers_view", "missing_view"),
            read_names=("orders_view", "customers_view", "missing_view"),
            expected_definitions=("SELECT 1", "SELECT 2", None),
            expected_query_count=1,
        ),
        SnowflakeViewDefinitionsTestCase(
            description="a view outside the prefetch is still read on its own",
            stored_rows=(("ORDERS_VIEW", "SELECT 1"), ("PRODUCTS_VIEW", "SELECT 3")),
            prefetched_names=("orders_view",),
            read_names=("orders_view", "products_view"),
            expected_definitions=("SELECT 1", "SELECT 3"),
            expected_query_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_prefetched_schema_when_reading_view_definitions_then_one_query_serves_them(
    test_case: SnowflakeViewDefinitionsTestCase,
) -> None:
    adapter: _ViewDefinitionAdapter = _ViewDefinitionAdapter(stored=test_case.stored_rows)
    connection: object = object()

    catalog: InspectionCatalog
    with open_inspection_catalog(adapter=adapter, connection=connection) as catalog:
        catalog.prefetch_view_definitions(
            requests=(("analytics_db", "analytics", test_case.prefetched_names),)
        )
        definitions: tuple[str | None, ...] = tuple(
            adapter.read_view_definition(
                connection=connection, database="analytics_db", schema="analytics", name=name
            )
            for name in test_case.read_names
        )

    assert definitions == test_case.expected_definitions
    assert len(adapter.queries) == test_case.expected_query_count
    assert "UPPER(TABLE_NAME) IN (" in adapter.queries[0]
