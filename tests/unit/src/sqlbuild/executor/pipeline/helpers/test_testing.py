"""Tests for SQL unit test pipeline helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationTarget,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ChainStep, PlanOutput, SqlTestPlanEntry
from sqlbuild.executor.pipeline.helpers.testing import run_test_pipeline
from sqlbuild.executor.testing.models import SqlTestExecutionResult
from tests.unit.src.sqlbuild.executor.pipeline.helpers._test_types import (
    SqlTestFunctionPreflightTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestFunctionPreflightTestCase(
            description="missing project function fails before running SQL test",
            expected_outcome="error",
            expected_error_fragment="Run `sqb build` first",
        ),
    ],
    ids=["missing project function fails before running SQL test"],
)
def test_given_sql_test_with_missing_function_when_running_pipeline_then_returns_setup_error(
    test_case: SqlTestFunctionPreflightTestCase,
    tmp_path: Path,
) -> None:
    function_key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.FUNCTION,
        name="missing_function",
    )
    plan: PlanOutput = PlanOutput(
        test_entries=(
            SqlTestPlanEntry(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SQL_TEST,
                    name="test_missing_function",
                ),
                name="test_missing_function",
                chain=(
                    ChainStep(
                        model_name="fact_orders",
                        resolved_sql="SELECT main.missing_function(1) AS value",
                        expected_cte_sql="SELECT 2 AS value",
                    ),
                ),
                function_deps=(function_key,),
            ),
        ),
        function_targets={
            "missing_function": CompiledRelationTarget(
                database=None,
                schema="main",
                name="missing_function",
                qualified_name="main.missing_function",
            )
        },
    )

    results: tuple[SqlTestExecutionResult, ...] = run_test_pipeline(
        plan=plan,
        connection_config={"database": str(tmp_path / "test.duckdb")},
        adapter=DuckDbAdapter(),
    )

    assert len(results) == 1
    assert results[0].outcome == test_case.expected_outcome
    assert results[0].error_message is not None
    assert test_case.expected_error_fragment in results[0].error_message
