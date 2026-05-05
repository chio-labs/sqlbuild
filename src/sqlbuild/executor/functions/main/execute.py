"""SQL function execution helpers."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.types import FunctionLanguage
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
        if (
            function_entry.language == FunctionLanguage.PYTHON
            and not adapter.supports_python_functions()
        ):
            raise NotImplementedError(
                f"Adapter '{type(adapter).__name__}' does not support Python UDFs"
            )
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
            language=function_entry.language,
            runtime_version=function_entry.runtime_version,
            entry_point=function_entry.entry_point,
            packages=function_entry.packages,
            source_file_path=function_entry.source_file_path,
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
