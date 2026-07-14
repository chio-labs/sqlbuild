from __future__ import annotations

import pytest

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.executor.testing._helpers import comparison_sql as comparison_sql_helpers
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from tests.unit.src.sqlbuild.executor.testing.main._test_types import (
    BuildComparisonSqlTestCase,
)
from tests.unit.src.sqlbuild.executor.testing.main.helpers import (
    build_assertion_test_entry,
    build_comparison_test_adapter,
    build_comparison_test_entry,
    build_comparison_test_entry_with_helper_ctes,
    build_table_function_test_entry,
)


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_adapter_when_building_comparison_sql_then_it_uses_expected_set_difference(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_comparison_test_entry(),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="disabled SQL analysis avoids parser formatting",
            adapter_name="duckdb",
            expected_fragments=(
                "SELECT 1 AS order_id",
                "SELECT 2 AS order_id",
            ),
            sql_analysis_enabled=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_formatting_disabled_when_building_comparison_sql_then_it_does_not_import_polyglot(
    test_case: BuildComparisonSqlTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)
    monkeypatch.setattr(
        comparison_sql_helpers,
        "import_polyglot_sql",
        lambda: pytest.fail("polyglot should not be imported when disabled"),
    )

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_comparison_test_entry(sql_analysis_enabled=test_case.sql_analysis_enabled),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="assertion test SQL counts zero-row assertion failures",
            adapter_name="duckdb",
            expected_fragments=(
                "__actual__orders AS",
                "__assert__no_negative_orders AS",
                "'assertion no_negative_orders' AS model_name",
                "0 AS expected_count",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_assertion_step_when_building_comparison_sql_then_it_counts_failing_rows(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_assertion_test_entry(),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="matching helper CTEs are lifted once from actual and expected SQL",
            adapter_name="duckdb",
            expected_fragments=(
                "input_values AS",
                "__actual__orders AS (",
                "__expected__orders AS (",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_matching_helper_ctes_when_building_comparison_sql_then_lifts_once(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_comparison_test_entry_with_helper_ctes(),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql
    assert comparison_sql.lower().count("input_values as") == 1


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="databricks quoted table function names preserve case",
            adapter_name="databricks",
            expected_fragments=("`workspace`.`test`.`customer_orders`(1)",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_databricks_table_fn_when_building_comparison_sql_then_preserves_case(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_table_function_test_entry(),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql
    assert "`workspace`.`test`.`CUSTOMER_ORDERS`" not in comparison_sql
    assert "\n" in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="bigquery quoted table function names preserve hyphenated project id",
            adapter_name="bigquery",
            expected_fragments=("`project-d5f92072-d107-4987-9ef.test.customer_orders`(1)",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_bigquery_table_fn_when_building_comparison_sql_then_preserves_backticks(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_table_function_test_entry(
            resolved_sql=("SELECT * FROM `project-d5f92072-d107-4987-9ef.test.customer_orders`(1)")
        ),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql
    assert "project-d5f92072-d107-4987-9ef.test.customer_orders(1)" not in comparison_sql
