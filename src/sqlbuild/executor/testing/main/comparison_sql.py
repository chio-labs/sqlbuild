"""Build executable SQL unit-test comparison queries."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing._helpers.comparison_sql import (
    build_chain_comparison_parts,
    format_sql,
    lift_step_ctes,
    unique_cte_suffix,
)


def build_sql_test_comparison_sql(
    *,
    test_entry: SqlTestPlanEntry,
    set_difference_operator: str = "EXCEPT",
    sql_analysis_dialect: str | None = None,
) -> str:
    """Build the single SQL statement used to execute a SQL unit test."""

    if not test_entry.chain and not test_entry.assertions:
        return ""

    lifted_ctes, comparison_ctes, select_parts, cte_name_counts = build_chain_comparison_parts(
        test_entry=test_entry,
        set_difference_operator=set_difference_operator,
    )
    assertion_index: int
    for assertion_index, assertion in enumerate(test_entry.assertions, start=len(test_entry.chain)):
        assertion_suffix: str
        assertion_suffix, cte_name_counts = unique_cte_suffix(
            model_name=assertion.name,
            cte_name_counts=cte_name_counts,
        )
        assertion_cte: str = f"__assert__{assertion_suffix}"
        assertion_sql: str
        assertion_sql, lifted_ctes = lift_step_ctes(
            sql=assertion.resolved_sql,
            lifted_ctes=lifted_ctes,
            sql_analysis_enabled=test_entry.sql_analysis_enabled,
        )
        comparison_ctes.append(f"{assertion_cte} AS ({assertion_sql})")
        select_parts.append(
            "SELECT "
            f"{assertion_index} AS step_index, "
            f"'assertion {_escape_sql_string(assertion.name)}' AS model_name, "
            f"(SELECT COUNT(*) FROM {assertion_cte}) AS actual_count, "
            "0 AS expected_count, "
            f"(SELECT COUNT(*) FROM {assertion_cte}) AS unexpected_count, "
            "0 AS missing_count"
        )
    cte_parts: list[str] = [f"{name} AS ({sql})" for name, sql in lifted_ctes.items()]
    cte_parts.extend(comparison_ctes)
    if not select_parts:
        return ""
    comparison_sql: str = f"WITH {', '.join(cte_parts)} " + " UNION ALL ".join(select_parts)
    return format_sql(
        sql=comparison_sql,
        sql_analysis_dialect=sql_analysis_dialect,
        sql_analysis_enabled=test_entry.sql_analysis_enabled,
    )


def _escape_sql_string(value: str) -> str:
    """Escape a Python string for a single-quoted SQL string literal."""

    return value.replace("'", "''")
