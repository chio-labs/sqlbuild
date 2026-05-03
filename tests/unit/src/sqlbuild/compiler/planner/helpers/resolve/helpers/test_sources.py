"""Tests for source reference resolution."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.planner.helpers.resolve.helpers.sources import (
    resolve_source_references,
)
from sqlbuild.spec.models.source import SourceColumnEntry, SourceEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers.resolve.helpers._test_types import (
    SourceResolutionTestCase,
)

_ENFORCED_SOURCE: SourceEntry = SourceEntry(
    name="raw_orders",
    database="raw",
    schema="public",
    table="orders",
    type_enforcement=True,
    columns=(
        SourceColumnEntry(name="order_id", type="VARCHAR"),
        SourceColumnEntry(name="status", type="INTEGER"),
    ),
)

_ENFORCED_WAREHOUSE_COLUMNS: dict[str, tuple[ColumnInfo, ...]] = {
    "raw_orders": (
        ColumnInfo(name="order_id", type="VARCHAR"),
        ColumnInfo(name="status", type="VARCHAR"),
        ColumnInfo(name="amount", type="DECIMAL"),
    ),
}

TEST_CASES: list[SourceResolutionTestCase] = [
    SourceResolutionTestCase(
        description="replaces source with qualified name when no enforcement",
        query_sql='SELECT * FROM __source("raw_orders")',
        star_exclude_keyword="EXCLUDE",
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders",
                database="raw",
                schema="public",
                table="orders",
                type_enforcement=False,
                columns=(
                    SourceColumnEntry(name="order_id", type="VARCHAR"),
                    SourceColumnEntry(name="status", type="INTEGER"),
                ),
            ),
        },
        source_warehouse_columns=_ENFORCED_WAREHOUSE_COLUMNS,
        expected_sql="SELECT * FROM raw.public.orders",
    ),
    SourceResolutionTestCase(
        description="wraps query expression source as subquery",
        query_sql='SELECT * FROM __source("raw_orders")',
        star_exclude_keyword="EXCLUDE",
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders",
                expression="SELECT 1 AS order_id, 'placed' AS status",
            ),
        },
        source_warehouse_columns={},
        expected_sql="SELECT * FROM (SELECT 1 AS order_id, 'placed' AS status)",
    ),
    SourceResolutionTestCase(
        description="keeps table function expression source unwrapped",
        query_sql='SELECT * FROM __source("raw_orders")',
        star_exclude_keyword="EXCLUDE",
        source_map={"raw_orders": SourceEntry(name="raw_orders", expression="range(3)")},
        source_warehouse_columns={},
        expected_sql="SELECT * FROM range(3)",
    ),
    SourceResolutionTestCase(
        description="casts expression source declared typed columns",
        query_sql='SELECT * FROM __source("raw_orders")',
        star_exclude_keyword="EXCLUDE",
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders",
                expression="SELECT '1' AS order_id, 12 AS amount",
                type_enforcement=True,
                columns=(
                    SourceColumnEntry(name="order_id", type="INTEGER"),
                    SourceColumnEntry(name="amount", type="DECIMAL"),
                ),
            ),
        },
        source_warehouse_columns={},
        expected_sql=(
            "SELECT * FROM (SELECT CAST(order_id AS INTEGER) AS order_id, "
            "CAST(amount AS DECIMAL) AS amount "
            "FROM (SELECT '1' AS order_id, 12 AS amount))"
        ),
    ),
    SourceResolutionTestCase(
        description="replaces source with CAST subquery when enforcement enabled",
        query_sql='SELECT * FROM __source("raw_orders")',
        star_exclude_keyword="EXCLUDE",
        source_map={"raw_orders": _ENFORCED_SOURCE},
        source_warehouse_columns=_ENFORCED_WAREHOUSE_COLUMNS,
        expected_sql=(
            "SELECT * FROM (SELECT * EXCLUDE (order_id, status), "
            "CAST(order_id AS VARCHAR) AS order_id, "
            "CAST(status AS INTEGER) AS status "
            "FROM raw.public.orders)"
        ),
    ),
    SourceResolutionTestCase(
        description="uses EXCEPT keyword for bigquery-style dialects",
        query_sql='SELECT * FROM __source("raw_orders")',
        star_exclude_keyword="EXCEPT",
        source_map={"raw_orders": _ENFORCED_SOURCE},
        source_warehouse_columns=_ENFORCED_WAREHOUSE_COLUMNS,
        expected_sql=(
            "SELECT * FROM (SELECT * EXCEPT (order_id, status), "
            "CAST(order_id AS VARCHAR) AS order_id, "
            "CAST(status AS INTEGER) AS status "
            "FROM raw.public.orders)"
        ),
    ),
    SourceResolutionTestCase(
        description="leaves unknown source references unchanged",
        query_sql='SELECT * FROM __source("unknown_source")',
        star_exclude_keyword="EXCLUDE",
        source_map={},
        source_warehouse_columns={},
        expected_sql='SELECT * FROM __source("unknown_source")',
    ),
    SourceResolutionTestCase(
        description="replaces multiple source references in one query",
        query_sql=(
            'SELECT a.*, b.* FROM __source("raw_orders") a '
            'JOIN __source("raw_customers") b ON a.id = b.id'
        ),
        star_exclude_keyword="EXCLUDE",
        source_map={
            "raw_orders": SourceEntry(
                name="raw_orders", database="raw", schema="public", table="orders"
            ),
            "raw_customers": SourceEntry(
                name="raw_customers", database="raw", schema="public", table="customers"
            ),
        },
        source_warehouse_columns={},
        expected_sql=(
            "SELECT a.*, b.* FROM raw.public.orders a JOIN raw.public.customers b ON a.id = b.id"
        ),
    ),
    SourceResolutionTestCase(
        description="builds qualified name with database schema and table",
        query_sql='SELECT * FROM __source("full_source")',
        star_exclude_keyword="EXCLUDE",
        source_map={
            "full_source": SourceEntry(
                name="full_source", database="mydb", schema="myschema", table="mytable"
            ),
        },
        source_warehouse_columns={},
        expected_sql="SELECT * FROM mydb.myschema.mytable",
    ),
    SourceResolutionTestCase(
        description="falls back to source name when table is not set",
        query_sql='SELECT * FROM __source("name_only")',
        star_exclude_keyword="EXCLUDE",
        source_map={"name_only": SourceEntry(name="name_only")},
        source_warehouse_columns={},
        expected_sql="SELECT * FROM name_only",
    ),
    SourceResolutionTestCase(
        description="enforcement skips columns not in warehouse",
        query_sql='SELECT * FROM __source("partial_source")',
        star_exclude_keyword="EXCLUDE",
        source_map={
            "partial_source": SourceEntry(
                name="partial_source",
                database="raw",
                schema="public",
                table="partial",
                type_enforcement=True,
                columns=(
                    SourceColumnEntry(name="order_id", type="VARCHAR"),
                    SourceColumnEntry(name="missing_col", type="INTEGER"),
                ),
            ),
        },
        source_warehouse_columns={
            "partial_source": (
                ColumnInfo(name="order_id", type="VARCHAR"),
                ColumnInfo(name="amount", type="DECIMAL"),
            ),
        },
        expected_sql=(
            "SELECT * FROM (SELECT * EXCLUDE (order_id), "
            "CAST(order_id AS VARCHAR) AS order_id "
            "FROM raw.public.partial)"
        ),
    ),
    SourceResolutionTestCase(
        description="all columns enforced uses plain SELECT without EXCLUDE",
        query_sql='SELECT * FROM __source("all_enforced")',
        star_exclude_keyword="EXCLUDE",
        source_map={
            "all_enforced": SourceEntry(
                name="all_enforced",
                database="raw",
                schema="public",
                table="all_cols",
                type_enforcement=True,
                columns=(
                    SourceColumnEntry(name="id", type="INTEGER"),
                    SourceColumnEntry(name="name", type="VARCHAR"),
                ),
            ),
        },
        source_warehouse_columns={
            "all_enforced": (
                ColumnInfo(name="id", type="BIGINT"),
                ColumnInfo(name="name", type="TEXT"),
            ),
        },
        expected_sql=(
            "SELECT * FROM (SELECT "
            "CAST(id AS INTEGER) AS id, "
            "CAST(name AS VARCHAR) AS name "
            "FROM raw.public.all_cols)"
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_source_references_when_resolving_then_returns_expected_sql(
    test_case: SourceResolutionTestCase,
) -> None:
    result: str = resolve_source_references(
        query_sql=test_case.query_sql,
        source_map=test_case.source_map,
        source_warehouse_columns=test_case.source_warehouse_columns,
        star_exclude_keyword=test_case.star_exclude_keyword,
        cursor_bounds=None,
        cursor_inputs={},
    )

    assert result == test_case.expected_sql
