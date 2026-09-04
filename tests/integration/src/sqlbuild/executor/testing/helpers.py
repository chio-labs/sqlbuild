"""Test helpers for SQL test executor integration tests."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, SqlTestPlanEntry
from sqlbuild.executor.testing.main._execute import execute_sql_test
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from tests.integration.src.sqlbuild.executor.testing._test_types import (
    SqlTestExecutionTestCase,
)


def build_sql_test_plan_entry(
    *,
    name: str,
    chain_steps: tuple[tuple[str, str, str | None], ...],
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
    assert (test_case.expected_error_fragment or "") in (result.error_message or "")
    models_by_outcome: dict[SqlTestOutcome, list[str]] = {outcome: [] for outcome in SqlTestOutcome}
    for step_result in result.step_results:
        models_by_outcome[step_result.outcome].append(step_result.model_name)
    failed_models: tuple[str, ...] = tuple(models_by_outcome[SqlTestOutcome.FAIL])
    assert failed_models == test_case.expected_failed_models
