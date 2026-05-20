"""Source loader execution."""

from __future__ import annotations

import time
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.helpers.rows import build_rows_sql, normalize_loader_rows
from sqlbuild.executor.load.models import LoaderContext, LoadExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.spec.models.source import SourceEntry


def execute_source_load(
    *,
    source_entry: SourceEntry,
    loader_function: DiscoveredLoaderFunction,
    adapter: BaseAdapter,
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    statement_recorder: StatementRecorder,
) -> LoadExecutionResult:
    """Run one source loader and write returned rows using the table strategy."""

    target_name: str = source_entry.table if source_entry.table is not None else source_entry.name
    staging_name: str = f"{target_name}__staging"
    target: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=source_entry.database,
        schema=source_entry.schema,
        name=target_name,
    )
    staging: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=source_entry.database,
        schema=source_entry.schema,
        name=staging_name,
    )
    start: float = time.monotonic()
    try:
        if loader_function.depends_on:
            raise ExecutorInputError(
                f"Source loader '{loader_function.name}' has dependencies, which sqb load does "
                "not support yet"
            )
        if source_entry.write_strategy != "table":
            raise ExecutorInputError(
                f"Source '{source_entry.name}' uses write_strategy "
                f"'{source_entry.write_strategy}', "
                "but sqb load currently supports only write_strategy table"
            )
        adapter.ensure_schema(
            connection,
            database=source_entry.database,
            schema=source_entry.schema,
            statement_recorder=statement_recorder,
        )
        context: LoaderContext = LoaderContext(
            adapter=adapter,
            connection=connection,
            target=target,
            target_database=source_entry.database,
            target_schema=source_entry.schema,
            target_name=target_name,
            run_id=run_id,
            environment=environment,
            vars=vars,
            is_reload=is_reload,
            statement_recorder=statement_recorder,
        )
        rows: tuple[dict[str, object], ...] = normalize_loader_rows(
            loader_function.function(context)
        )
        sql: str = build_rows_sql(rows=rows, columns=source_entry.columns)
        adapter.create_table_as(
            connection,
            target=staging,
            sql=sql,
            statement_recorder=statement_recorder,
        )
        adapter.replace_table_from_relation(
            connection,
            target=target,
            source=staging,
            statement_recorder=statement_recorder,
        )
        adapter.drop(
            connection,
            target=staging,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
    except Exception as error:
        return LoadExecutionResult(
            source_name=source_entry.name,
            loader_name=loader_function.name,
            status=ExecutionStatus.FAILED,
            target=target,
            staging_relation=staging,
            duration_ms=int((time.monotonic() - start) * 1000),
            lifecycle_events=statement_recorder.snapshot(),
            error_message=str(error),
        )
    return LoadExecutionResult(
        source_name=source_entry.name,
        loader_name=loader_function.name,
        status=ExecutionStatus.SUCCESS,
        target=target,
        staging_relation=staging,
        rows_loaded=len(rows),
        duration_ms=int((time.monotonic() - start) * 1000),
        lifecycle_events=statement_recorder.snapshot(),
    )
