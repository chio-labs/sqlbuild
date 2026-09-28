"""Unit coverage for compatibility view SQL and column alias composition."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.compiler.migrations.models import ColumnMigrationEvent
from sqlbuild.executor.migrations._helpers.old_name_views import (
    compose_column_aliases,
    render_old_name_view_select,
)
from sqlbuild.executor.migrations.models import OldNameViewSource
from tests.unit.src.sqlbuild.executor.migrations._helpers._test_types import (
    ComposeColumnAliasesTestCase,
    SnowflakeOldNameSqlTestCase,
)
from tests.unit.src.sqlbuild.executor.migrations._helpers.helpers import (
    column_rename,
    snowflake_location,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ComposeColumnAliasesTestCase(
            description="one rename aliases the new column back",
            renames=(("amount", "revenue"),),
            expected_aliases=(("amount", "revenue"),),
        ),
        ComposeColumnAliasesTestCase(
            description="chained renames alias the first name to the latest",
            renames=(("amount", "revenue"), ("revenue", "net_revenue")),
            expected_aliases=(("amount", "net_revenue"),),
        ),
        ComposeColumnAliasesTestCase(
            description="a rename back to the original name needs no alias",
            renames=(("amount", "revenue"), ("revenue", "amount")),
            expected_aliases=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_column_renames_when_composing_then_old_names_map_to_current(
    test_case: ComposeColumnAliasesTestCase,
) -> None:
    events: tuple[ColumnMigrationEvent, ...] = tuple(
        column_rename(origin=origin, destination=destination, day=day)
        for day, (origin, destination) in enumerate(test_case.renames, start=1)
    )

    assert compose_column_aliases(events) == test_case.expected_aliases


@pytest.mark.parametrize(
    "test_case",
    [
        SnowflakeOldNameSqlTestCase(
            description="view without aliases selects every column",
            column_aliases=(),
            expected_statements=(
                "CREATE OR REPLACE VIEW analytics.revenue AS SELECT * FROM analytics.daily_revenue",
            ),
        ),
        SnowflakeOldNameSqlTestCase(
            description="aliased column keeps its exact name and exposes the old one",
            column_aliases=(("amount", "revenue"),),
            expected_statements=(
                "CREATE OR REPLACE VIEW analytics.revenue AS "
                'SELECT "ORDER_ID", "REVENUE" AS "AMOUNT" FROM analytics.daily_revenue',
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_compatibility_view_when_rendering_then_sql_uses_snowflake_names(
    test_case: SnowflakeOldNameSqlTestCase, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter: SnowflakeAdapter = SnowflakeAdapter()

    def columns(**_: Any) -> tuple[ColumnInfo, ...]:
        return (
            ColumnInfo(name="ORDER_ID", type="NUMBER"),
            ColumnInfo(name="REVENUE", type="NUMBER"),
        )

    monkeypatch.setattr(adapter, "get_columns", columns)
    source: OldNameViewSource = OldNameViewSource(
        old=snowflake_location(adapter=adapter, name="revenue"),
        new=snowflake_location(adapter=adapter, name="daily_revenue"),
        column_aliases=test_case.column_aliases,
    )

    select_sql: str = render_old_name_view_select(adapter=adapter, connection=None, source=source)
    statements: tuple[str, ...] = adapter.render_create_view_as(
        destination=source.old.qualified_name or "", sql=select_sql
    )

    assert statements == test_case.expected_statements
    assert adapter.supports_old_name_views()
    assert not adapter.views_bind_to_relation_identity()
    assert adapter.render_create_old_name_view_state_table_sql(
        database=None, schema="analytics"
    ).startswith("CREATE TRANSIENT TABLE IF NOT EXISTS")
