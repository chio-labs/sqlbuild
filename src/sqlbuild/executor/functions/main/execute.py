"""SQL function execution helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.planner.models import FunctionPlanEntry
from sqlbuild.executor.build.models import FunctionExecutionResult
from sqlbuild.executor.shared.types import ExecutionStatus


def execute_function(
    *,
    function_entry: FunctionPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    statement_recorder: StatementRecorder,
) -> FunctionExecutionResult:
    """Create or replace one SQL function."""

    if function_entry.target.qualified_name is None:
        return FunctionExecutionResult(
            function_name=function_entry.name,
            status=ExecutionStatus.FAILED,
            error_message="function target could not be qualified",
        )
    try:
        adapter.ensure_schema(
            connection,
            database=function_entry.target.database,
            schema=function_entry.target.schema,
            statement_recorder=statement_recorder,
        )
        adapter.create_function(
            connection,
            target=function_entry.target.qualified_name,
            arguments=function_entry.arguments,
            returns=function_entry.returns,
            body_sql=function_entry.body_sql,
            statement_recorder=statement_recorder,
        )
        return FunctionExecutionResult(
            function_name=function_entry.name,
            status=ExecutionStatus.SUCCESS,
            lifecycle_events=statement_recorder.snapshot(),
        )
    except Exception as error:
        return FunctionExecutionResult(
            function_name=function_entry.name,
            status=ExecutionStatus.FAILED,
            error_message=str(error),
            lifecycle_events=statement_recorder.snapshot(),
        )
