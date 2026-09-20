"""Build executable SQL unit-test comparison queries."""

from __future__ import annotations

import json
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.planner.main.execution.sql_test_dialect import (
    restore_sql_test_dialect_function_names,
)
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing._helpers.comparison_sql import (
    build_chain_comparison_parts,
    cte_definition_sql,
    lift_preanalyzed_step_ctes,
    lift_step_ctes,
    unique_cte_suffix,
)
from sqlbuild.executor.testing.types import NativeSqlTestRenderingModule


def build_sql_test_comparison_sql_batch(
    *,
    test_entries: tuple[SqlTestPlanEntry, ...],
    set_difference_operator: str = "EXCEPT",
    sql_analysis_dialect: str | None = None,
) -> tuple[str, ...]:
    """Build comparison SQL for a deterministic batch of planned SQL tests."""

    if not test_entries:
        return ()
    requests: list[dict[str, object]] = []
    for test_entry in test_entries:
        requests.append(
            {
                "chain": [
                    {
                        "modelName": step.model_name,
                        "resolvedSql": step.resolved_sql,
                        "expectedCteSql": step.expected_cte_sql,
                        "liftedCtes": step.lifted_ctes,
                        "comparisonBodySql": step.comparison_body_sql,
                    }
                    for step in test_entry.chain
                ],
                "assertions": [
                    {
                        "name": assertion.name,
                        "resolvedSql": assertion.resolved_sql,
                        "liftedCtes": assertion.lifted_ctes,
                        "comparisonBodySql": assertion.comparison_body_sql,
                    }
                    for assertion in test_entry.assertions
                ],
                "sqlAnalysisEnabled": test_entry.sql_analysis_enabled,
                "setDifferenceOperator": set_difference_operator,
                "sqlAnalysisDialect": sql_analysis_dialect,
            }
        )
    response: object = json.loads(
        cast(NativeSqlTestRenderingModule, _native).render_sql_test_comparisons_json(
            json.dumps(
                {"requests": requests, "workers": 4},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    )
    if not isinstance(response, list) or len(response) != len(test_entries):
        raise RuntimeError("native SQL-test rendering returned an invalid batch response")
    rendered: list[str] = []
    for item in response:
        item_dict: dict[str, Any] | None = (
            cast(dict[str, Any], item) if isinstance(item, dict) else None
        )
        sql: object = item_dict.get("sql") if item_dict is not None else None
        if not isinstance(sql, str):
            raise RuntimeError("native SQL-test rendering returned an invalid result")
        rendered.append(
            restore_sql_test_dialect_function_names(
                sql=sql,
                dialect=sql_analysis_dialect,
            )
        )
    return tuple(rendered)


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
        if assertion.lifted_ctes:
            assertion_sql, lifted_ctes = lift_preanalyzed_step_ctes(
                sql=assertion.comparison_body_sql or assertion.resolved_sql,
                preanalyzed_ctes=assertion.lifted_ctes,
                lifted_ctes=lifted_ctes,
                sql_analysis_enabled=test_entry.sql_analysis_enabled,
            )
        else:
            assertion_sql, lifted_ctes = lift_step_ctes(
                sql=assertion.resolved_sql,
                lifted_ctes=lifted_ctes,
                sql_analysis_enabled=test_entry.sql_analysis_enabled,
            )
        comparison_ctes.append(cte_definition_sql(name=assertion_cte, sql=assertion_sql))
        select_parts.append(
            "SELECT "
            f"{assertion_index} AS step_index, "
            f"'assertion {_escape_sql_string(assertion.name)}' AS model_name, "
            f"(SELECT COUNT(*) FROM {assertion_cte}) AS actual_count, "
            "0 AS expected_count, "
            f"(SELECT COUNT(*) FROM {assertion_cte}) AS unexpected_count, "
            "0 AS missing_count"
        )
    cte_parts: list[str] = [
        cte_definition_sql(name=name, sql=sql) for name, sql in lifted_ctes.items()
    ]
    cte_parts.extend(comparison_ctes)
    if not select_parts:
        return ""
    comparison_sql: str = "WITH " + ",\n".join(cte_parts) + "\n"
    comparison_sql += "\nUNION ALL\n".join(select_parts)
    return restore_sql_test_dialect_function_names(
        sql=comparison_sql,
        dialect=sql_analysis_dialect,
    )


def _escape_sql_string(value: str) -> str:
    """Escape a Python string for a single-quoted SQL string literal."""

    return value.replace("'", "''")
