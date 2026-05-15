"""SQL function execution helpers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.fingerprints.main.write import write_fingerprint
from sqlbuild.compiler.fingerprints.models import Fingerprint
from sqlbuild.compiler.planner.models import FunctionPlanEntry
from sqlbuild.executor.build.models import FunctionExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus


def execute_function(
    *,
    function_entry: FunctionPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    statement_recorder: StatementRecorder,
    run_id: str,
    query_change_tracking: bool,
) -> FunctionExecutionResult:
    """Create or replace one SQL function."""

    if function_entry.target.qualified_name is None:
        return FunctionExecutionResult(
            function_name=function_entry.name,
            status=ExecutionStatus.FAILED,
            error_message="function target could not be qualified",
        )
    warnings: list[str] = []
    try:
        if (
            function_entry.language == FunctionLanguage.PYTHON
            and not adapter.supports_python_functions()
        ):
            raise ExecutorInputError(
                f"Adapter '{type(adapter).__name__}' does not support Python UDFs"
            )
        if function_entry.return_columns and not adapter.supports_table_functions():
            raise ExecutorInputError(
                f"Adapter '{type(adapter).__name__}' does not support SQL table functions"
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
            return_columns=function_entry.return_columns,
            language=function_entry.language,
            runtime_version=function_entry.runtime_version,
            entry_point=function_entry.entry_point,
            packages=function_entry.packages,
            source_file_path=function_entry.source_file_path,
            statement_recorder=statement_recorder,
        )
        _try_write_function_fingerprint(
            entry=function_entry,
            adapter=adapter,
            connection=connection,
            run_id=run_id,
            query_change_tracking=query_change_tracking,
            warnings=warnings,
            statement_recorder=statement_recorder,
        )
        return FunctionExecutionResult(
            function_name=function_entry.name,
            status=ExecutionStatus.SUCCESS,
            warning_messages=tuple(warnings),
            lifecycle_events=statement_recorder.snapshot(),
        )
    except Exception as error:
        return FunctionExecutionResult(
            function_name=function_entry.name,
            status=ExecutionStatus.FAILED,
            error_message=str(error),
            warning_messages=tuple(warnings),
            lifecycle_events=statement_recorder.snapshot(),
        )


def _try_write_function_fingerprint(
    *,
    entry: FunctionPlanEntry,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    query_change_tracking: bool,
    warnings: list[str],
    statement_recorder: StatementRecorder,
) -> None:
    if not query_change_tracking:
        return
    fingerprint_schema: str | None = entry.fingerprint_target.schema
    target_is_unqualified: bool = entry.target.schema is None and entry.target.database is None
    if target_is_unqualified and not adapter.supports_unqualified_function_fingerprints():
        fingerprint_schema = None
    if fingerprint_schema is None:
        warnings.append(
            "fingerprint write skipped for "
            f"function '{entry.name}': fingerprint schema is missing while "
            "query_change_tracking is enabled"
        )
        return
    try:
        adapter.ensure_schema(
            connection,
            database=entry.fingerprint_target.database,
            schema=fingerprint_schema,
            statement_recorder=statement_recorder,
        )
        normalized_sql: str = " ".join(entry.fingerprint_query_sql.split())
        query_hash: str = hashlib.sha256(normalized_sql.encode()).hexdigest()
        schema_fp: str = hashlib.sha256(b"").hexdigest()
        fingerprint: Fingerprint = Fingerprint(
            model_name=entry.name,
            target_database=entry.target.database,
            target_schema=entry.target.schema,
            target_name=entry.target.name,
            run_id=run_id,
            query_hash=query_hash,
            ast_hash=None,
            schema_fingerprint=schema_fp,
            query_sql=entry.fingerprint_query_sql,
            ts=datetime.now(tz=UTC),
        )
        write_fingerprint(
            connection=connection,
            execute=adapter.execute,
            database=entry.fingerprint_target.database,
            schema=fingerprint_schema,
            fingerprint=fingerprint,
            render_qualified_name=adapter.render_qualified_name,
            render_framework_type=adapter.render_framework_type,
        )
    except Exception as exc:
        warnings.append(
            f"fingerprint write failed for function '{entry.name}'; "
            f"future function-change detection may be incorrect: {exc}"
        )
