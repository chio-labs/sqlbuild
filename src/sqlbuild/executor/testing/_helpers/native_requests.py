"""Serialize planned SQL-test steps for the native comparison renderer."""

from __future__ import annotations

from sqlbuild.compiler.planner.models import ChainStep, SqlTestAssertionStep, SqlTestPlanEntry


def comparison_request(
    *,
    test_entry: SqlTestPlanEntry,
    set_difference_operator: str,
    sql_analysis_dialect: str | None,
) -> dict[str, object]:
    """Serialize one planned test into a native comparison render request."""

    return {
        "chain": [chain_step_request(step=step) for step in test_entry.chain],
        "assertions": [
            assertion_step_request(assertion=assertion) for assertion in test_entry.assertions
        ],
        "sqlAnalysisEnabled": test_entry.sql_analysis_enabled,
        "setDifferenceOperator": set_difference_operator,
        "sqlAnalysisDialect": sql_analysis_dialect,
    }


def chain_step_request(*, step: ChainStep) -> dict[str, object]:
    """Serialize one planned chain step for the native renderer."""

    return {
        "modelName": step.model_name,
        "resolvedSql": step.resolved_sql,
        "expectedCteSql": step.expected_cte_sql,
        "liftedCtes": step.lifted_ctes,
        "comparisonBodySql": step.comparison_body_sql,
        "expectedColumns": step.expected_columns,
        "expectedLiftedCtes": step.expected_lifted_ctes,
    }


def assertion_step_request(*, assertion: SqlTestAssertionStep) -> dict[str, object]:
    """Serialize one planned assertion step for the native renderer."""

    return {
        "name": assertion.name,
        "resolvedSql": assertion.resolved_sql,
        "liftedCtes": assertion.lifted_ctes,
        "comparisonBodySql": assertion.comparison_body_sql,
    }
