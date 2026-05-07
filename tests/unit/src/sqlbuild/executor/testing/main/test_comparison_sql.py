from __future__ import annotations

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from sqlbuild.executor.testing.main.helpers import comparison_sql as comparison_sql_helpers
from tests.unit.src.sqlbuild.executor.testing.main._test_types import (
    BuildComparisonSqlTestCase,
)
from tests.unit.src.sqlbuild.executor.testing.main.helpers import (
    build_comparison_test_adapter,
    build_comparison_test_entry,
)

TEST_CASES: list[BuildComparisonSqlTestCase] = [
    BuildComparisonSqlTestCase(
        description="duckdb comparison sql uses EXCEPT",
        adapter_name="duckdb",
        expected_fragments=(
            "FROM __actual__orders",
            "FROM __expected__orders",
            "EXCEPT",
        ),
    ),
    BuildComparisonSqlTestCase(
        description="snowflake comparison sql uses EXCEPT",
        adapter_name="snowflake",
        expected_fragments=(
            "FROM __actual__orders",
            "FROM __expected__orders",
            "EXCEPT",
        ),
    ),
    BuildComparisonSqlTestCase(
        description="bigquery comparison sql preserves EXCEPT DISTINCT formatting",
        adapter_name="bigquery",
        expected_fragments=(
            "FROM __actual__orders",
            "FROM __expected__orders",
            "EXCEPT DISTINCT",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_adapter_when_building_comparison_sql_then_it_uses_expected_set_difference(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)

    comparison_sql: str = build_sql_test_comparison_sql(
        build_comparison_test_entry(),
        set_difference_operator=adapter.render_set_difference_operator(),
        sqlglot_dialect=adapter.sqlglot_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="disabled sqlglot builds comparison sql without importing sqlglot",
            adapter_name="duckdb",
            expected_fragments=(
                "SELECT 1 AS order_id",
                "SELECT 2 AS order_id",
            ),
            sqlglot_enabled=False,
        )
    ],
    ids=["disabled sqlglot builds comparison sql without importing sqlglot"],
)
def test_given_sqlglot_disabled_when_building_comparison_sql_then_it_does_not_import_sqlglot(
    test_case: BuildComparisonSqlTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)
    monkeypatch.setattr(
        comparison_sql_helpers,
        "import_sqlglot",
        lambda: pytest.fail("sqlglot should not be imported when disabled"),
    )

    comparison_sql: str = build_sql_test_comparison_sql(
        build_comparison_test_entry(sqlglot_enabled=test_case.sqlglot_enabled),
        set_difference_operator=adapter.render_set_difference_operator(),
        sqlglot_dialect=adapter.sqlglot_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql
