"""Build batches of executable SQL unit-test comparison queries."""

from __future__ import annotations

import json
from typing import Any, cast

import sqlbuild._native as _native
from sqlbuild.compiler.planner.main.execution.sql_test_dialect import (
    restore_sql_test_dialect_function_names,
)
from sqlbuild.compiler.planner.models import SqlTestPlanEntry
from sqlbuild.executor.testing._helpers.comparison_sql import format_sql
from sqlbuild.executor.testing.exceptions import SqlTestRenderingError
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
        raise SqlTestRenderingError("native SQL-test rendering returned an invalid batch response")
    rendered: list[str] = []
    for item in response:
        item_dict: dict[str, Any] | None = (
            cast(dict[str, Any], item) if isinstance(item, dict) else None
        )
        sql: object = item_dict.get("sql") if item_dict is not None else None
        if not isinstance(sql, str):
            raise SqlTestRenderingError("native SQL-test rendering returned an invalid result")
        rendered.append(
            format_sql(
                sql=restore_sql_test_dialect_function_names(
                    sql=sql,
                    dialect=sql_analysis_dialect,
                ),
                sql_analysis_dialect=sql_analysis_dialect,
                sql_analysis_enabled=test_entries[len(rendered)].sql_analysis_enabled,
            )
        )
    return tuple(rendered)
