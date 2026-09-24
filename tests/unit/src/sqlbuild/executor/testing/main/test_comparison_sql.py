from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from sqlbuild.executor.testing.main.comparison_sql_batch import (
    build_sql_test_comparison_sql_batch,
)
from tests.unit.src.sqlbuild.executor.testing.main._test_types import (
    BuildComparisonSqlTestCase,
    ExpectedBooleanTestCase,
)
from tests.unit.src.sqlbuild.executor.testing.main.helpers import (
    build_assertion_test_entry,
    build_comparison_test_adapter,
    build_comparison_test_entry,
    build_comparison_test_entry_with_helper_ctes,
    build_table_function_test_entry,
    build_transitive_comparison_test_entry,
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
        BuildComparisonSqlTestCase(
            description="sqlserver comparison aliases the set difference derived table",
            adapter_name="sqlserver",
            expected_fragments=(
                "FROM __actual__orders",
                "FROM __expected__orders",
                "EXCEPT",
                ") AS __sqlbuild_mismatch",
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
    expected_absent_fragment: str
    for expected_absent_fragment in test_case.expected_absent_fragments:
        assert expected_absent_fragment not in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="Snowflake comparison lifting preserves STARTSWITH",
            adapter_name="snowflake",
            expected_fragments=("STARTSWITH(name, 'A')", "picked AS ("),
            expected_absent_fragments=("STARTS_WITH",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_snowflake_function_when_lifting_comparison_ctes_then_emits_supported_spelling(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)
    entry: SqlTestPlanEntry = replace(
        build_comparison_test_entry(),
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql=(
                    "WITH picked AS (SELECT STARTSWITH(name, 'A') AS matches FROM items) "
                    "SELECT matches FROM picked"
                ),
                expected_cte_sql="SELECT TRUE AS matches",
            ),
        ),
    )

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=entry,
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql
    for expected_absent_fragment in test_case.expected_absent_fragments:
        assert expected_absent_fragment not in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [
        BuildComparisonSqlTestCase(
            description="disabled SQL analysis keeps step SQL verbatim",
            adapter_name="duckdb",
            expected_fragments=(
                "__actual__orders AS (with Picked as (select 1 as order_id) select * from Picked)",
                "__expected__orders AS (SELECT 2 AS order_id)",
            ),
            sql_analysis_enabled=False,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_sql_analysis_disabled_when_building_comparison_sql_then_step_sql_is_not_regenerated(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    adapter: BaseAdapter = build_comparison_test_adapter(test_case.adapter_name)
    entry: SqlTestPlanEntry = replace(
        build_comparison_test_entry(sql_analysis_enabled=test_case.sql_analysis_enabled),
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql="with Picked as (select 1 as order_id) select * from Picked",
                expected_cte_sql="SELECT 2 AS order_id",
            ),
        ),
    )

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=entry,
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
    (
        BuildComparisonSqlTestCase(
            description="unasserted transitive step is omitted",
            adapter_name="duckdb",
            expected_fragments=("__actual__final_orders AS", "__expected__final_orders AS"),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unasserted_transitive_steps_when_building_comparison_then_emits_only_expected_model(
    test_case: BuildComparisonSqlTestCase,
) -> None:
    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=build_transitive_comparison_test_entry(),
    )

    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in comparison_sql
    assert "__actual__stg_orders AS" not in comparison_sql
    assert comparison_sql.lower().count("shared as") == 1


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


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanTestCase(description="authored CTEs are lifted", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_preanalyzed_step_with_authored_cte_when_building_comparison_then_lifts_both_ctes(
    test_case: ExpectedBooleanTestCase,
) -> None:
    entry: SqlTestPlanEntry = build_comparison_test_entry()
    entry = replace(
        entry,
        chain=(
            ChainStep(
                model_name="orders",
                resolved_sql=(
                    "WITH __ref__raw_orders AS (SELECT 1 AS order_id), "
                    "picked AS (SELECT * FROM __ref__raw_orders) SELECT * FROM picked"
                ),
                comparison_body_sql=(
                    "WITH picked AS (SELECT * FROM __ref__raw_orders) SELECT * FROM picked"
                ),
                lifted_ctes=(("__ref__raw_orders", "SELECT 1 AS order_id"),),
                expected_cte_sql="SELECT 1 AS order_id",
            ),
        ),
    )

    comparison_sql: str = build_sql_test_comparison_sql(
        test_entry=entry,
        sql_analysis_dialect="tsql",
    )

    assert (
        comparison_sql.index("__ref__raw_orders AS") < comparison_sql.index("picked AS")
    ) is test_case.expected_result
    assert comparison_sql.index("picked AS") < comparison_sql.index("__actual__orders AS")
    assert "__actual__orders AS (\nWITH picked" not in comparison_sql


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanTestCase(description="batch matches single renders", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_representative_plans_when_rendering_batch_then_matches_single_renders(
    test_case: ExpectedBooleanTestCase,
) -> None:
    entries: tuple[SqlTestPlanEntry, ...] = (
        build_comparison_test_entry(),
        build_comparison_test_entry_with_helper_ctes(),
        build_transitive_comparison_test_entry(),
        build_assertion_test_entry(),
    )
    expected: tuple[str, ...] = tuple(
        build_sql_test_comparison_sql(test_entry=entry, sql_analysis_dialect="duckdb")
        for entry in entries
    )

    actual: tuple[str, ...] = build_sql_test_comparison_sql_batch(
        test_entries=entries,
        sql_analysis_dialect="duckdb",
    )

    assert (actual == expected) is test_case.expected_result


@pytest.mark.parametrize(
    "test_case",
    [ExpectedBooleanTestCase(description="quoted table function matches", expected_result=True)],
    ids=lambda case: case.description,
)
def test_given_quoted_table_function_when_rendering_batch_then_matches_single_render(
    test_case: ExpectedBooleanTestCase,
) -> None:
    entry: SqlTestPlanEntry = build_table_function_test_entry(
        resolved_sql="SELECT * FROM `project-d5f92072-d107-4987-9ef.test.customer_orders`(1)"
    )
    adapter: BaseAdapter = build_comparison_test_adapter("bigquery")
    expected: str = build_sql_test_comparison_sql(
        test_entry=entry,
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    (actual,) = build_sql_test_comparison_sql_batch(
        test_entries=(entry,),
        set_difference_operator=adapter.render_set_difference_operator(),
        sql_analysis_dialect=adapter.sql_analysis_dialect(),
    )

    assert (actual == expected) is test_case.expected_result
