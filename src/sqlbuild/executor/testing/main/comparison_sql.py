"""Build executable SQL unit-test comparison queries."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing.main.comparison_sql_batch import (
    build_sql_test_comparison_sql_batch,
)


def build_sql_test_comparison_sql(
    *,
    test_entry: SqlTestPlanEntry,
    set_difference_operator: str = "EXCEPT",
    sql_analysis_dialect: str | None = None,
) -> str:
    """Build the single SQL statement used to execute a SQL unit test."""

    (comparison_sql,) = build_sql_test_comparison_sql_batch(
        test_entries=(test_entry,),
        set_difference_operator=set_difference_operator,
        sql_analysis_dialect=sql_analysis_dialect,
    )
    return comparison_sql
