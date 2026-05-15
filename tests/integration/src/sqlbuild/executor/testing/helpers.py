"""Test helpers for SQL test executor integration tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.compiler.compile.models.core import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.executor.testing.main.execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from tests.integration.src.sqlbuild.executor.testing._test_types import (
    SqlTestExecutionTestCase,
)


def build_sql_test_plan_entry(
    *,
    name: str,
    chain_steps: tuple[tuple[str, str, str], ...],
) -> SqlTestPlanEntry:
    """Build a SqlTestPlanEntry from (model_name, resolved_sql, expected_cte_sql) tuples."""

    chain: tuple[ChainStep, ...] = tuple(
        ChainStep(
            model_name=step[0],
            resolved_sql=step[1],
            expected_cte_sql=step[2],
        )
        for step in chain_steps
    )
    scope_deps: tuple[CompiledObjectKey, ...] = tuple(
        CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=step[0])
        for step in chain_steps
    )
    return SqlTestPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.SQL_TEST, name=name),
        name=name,
        chain=chain,
        scope_deps=scope_deps,
    )


def run_sql_test(
    *,
    test_case: SqlTestExecutionTestCase,
    adapter: DuckDbAdapter,
    connection: Any,
) -> SqlTestExecutionResult:
    """Execute a SQL test case and return the result."""

    entry: SqlTestPlanEntry = build_sql_test_plan_entry(
        name="test_model",
        chain_steps=test_case.chain_steps,
    )
    return execute_sql_test(
        test_entry=entry,
        adapter=adapter,
        connection=connection,
    )


def verify_test_result(
    *,
    result: SqlTestExecutionResult,
    test_case: SqlTestExecutionTestCase,
) -> None:
    """Verify SQL test execution result fields."""

    assert len(result.step_results) == test_case.expected_step_count
    if test_case.expected_error_fragment is not None:
        assert result.error_message is not None
        assert test_case.expected_error_fragment in result.error_message
    failed_models: tuple[str, ...] = tuple(
        r.model_name for r in result.step_results if r.outcome == SqlTestOutcome.FAIL
    )
    assert failed_models == test_case.expected_failed_models
