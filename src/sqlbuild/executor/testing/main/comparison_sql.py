"""Build executable SQL unit-test comparison queries."""

from __future__ import annotations

from collections import OrderedDict

from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.executor.testing.main.helpers.comparison_sql import (
    format_sql,
    lift_step_ctes,
    unique_cte_suffix,
)


def build_sql_test_comparison_sql(test_entry: SqlTestPlanEntry) -> str:
    """Build the single SQL statement used to execute a SQL unit test."""

    if not test_entry.chain:
        return ""

    lifted_ctes: OrderedDict[str, str] = OrderedDict()
    comparison_ctes: list[str] = []
    select_parts: list[str] = []
    cte_name_counts: dict[str, int] = {}
    step_index: int
    step: ChainStep
    for step_index, step in enumerate(test_entry.chain):
        cte_suffix: str = unique_cte_suffix(
            model_name=step.model_name,
            cte_name_counts=cte_name_counts,
        )
        actual_cte: str = f"__actual__{cte_suffix}"
        expected_cte: str = f"__expected__{cte_suffix}"
        actual_sql: str = lift_step_ctes(step.resolved_sql, lifted_ctes)
        comparison_ctes.append(f"{actual_cte} AS ({actual_sql})")
        comparison_ctes.append(f"{expected_cte} AS ({step.expected_cte_sql})")
        select_parts.append(
            "SELECT "
            f"{step_index} AS step_index, "
            f"'{_escape_sql_string(step.model_name)}' AS model_name, "
            f"(SELECT COUNT(*) FROM {actual_cte}) AS actual_count, "
            f"(SELECT COUNT(*) FROM {expected_cte}) AS expected_count, "
            f"(SELECT COUNT(*) FROM ("
            f"SELECT * FROM {actual_cte} EXCEPT SELECT * FROM {expected_cte}"
            f")) AS mismatched_count"
        )
    cte_parts: list[str] = [f"{name} AS ({sql})" for name, sql in lifted_ctes.items()]
    cte_parts.extend(comparison_ctes)
    comparison_sql: str = f"WITH {', '.join(cte_parts)} " + " UNION ALL ".join(select_parts)
    return format_sql(comparison_sql)


def _escape_sql_string(value: str) -> str:
    """Escape a Python string for a single-quoted SQL string literal."""

    return value.replace("'", "''")
