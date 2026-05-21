"""Source loader execution."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.executor.load.helpers.staging import write_loader_rows_to_staging
from sqlbuild.executor.load.models import LoaderContext, LoadExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


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
        supported_write_strategies: frozenset[SourceWriteStrategy] = frozenset(
            {
                SourceWriteStrategy.APPEND,
                SourceWriteStrategy.MERGE,
                SourceWriteStrategy.TABLE,
            }
        )
        if (
            source_entry.write_strategy is not None
            and source_entry.write_strategy not in supported_write_strategies
        ):
            raise ExecutorInputError(
                f"Source '{source_entry.name}' uses write_strategy "
                f"'{source_entry.write_strategy}', "
                "but sqb load currently supports only write_strategy append, merge, and table"
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
            current_cursor_value=_load_current_cursor_value(
                adapter=adapter,
                connection=connection,
                source_entry=source_entry,
                target=target,
                target_name=target_name,
                statement_recorder=statement_recorder,
            ),
            logger=logging.getLogger(f"sqlbuild.loader.{loader_function.name}"),
            statement_recorder=statement_recorder,
        )
        raw_rows: object = loader_function.function(context)
        if raw_rows is None:
            if source_entry.write_strategy is not None:
                raise ExecutorInputError(
                    f"Source '{source_entry.name}' defines write_strategy but loader "
                    f"'{loader_function.name}' returned no rows"
                )
            rows_loaded: int = 0
            return LoadExecutionResult(
                source_name=source_entry.name,
                loader_name=loader_function.name,
                status=ExecutionStatus.SUCCESS,
                target=target,
                staging_relation=None,
                rows_loaded=rows_loaded,
                duration_ms=int((time.monotonic() - start) * 1000),
                lifecycle_events=statement_recorder.snapshot(),
            )
        if source_entry.write_strategy is None:
            raise ExecutorInputError(
                f"Source '{source_entry.name}' loader '{loader_function.name}' returned rows "
                "but source has no write_strategy"
            )
        rows_loaded: int = write_loader_rows_to_staging(
            loader_return_value=raw_rows,
            source_entry=source_entry,
            adapter=adapter,
            connection=connection,
            staging=staging,
            statement_recorder=statement_recorder,
        )
        _apply_source_write_strategy(
            adapter=adapter,
            connection=connection,
            source_entry=source_entry,
            target=target,
            target_name=target_name,
            staging=staging,
            statement_recorder=statement_recorder,
        )
        adapter.drop(
            connection,
            target=staging,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
    except Exception as error:
        try:
            adapter.drop(
                connection,
                target=staging,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        except Exception:
            pass
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
        rows_loaded=rows_loaded,
        duration_ms=int((time.monotonic() - start) * 1000),
        lifecycle_events=statement_recorder.snapshot(),
    )


def _apply_source_write_strategy(
    *,
    adapter: BaseAdapter,
    connection: Any,
    source_entry: SourceEntry,
    target: str,
    target_name: str,
    staging: str,
    statement_recorder: StatementRecorder,
) -> None:
    if source_entry.write_strategy == SourceWriteStrategy.TABLE:
        adapter.replace_table_from_relation(
            connection,
            target=target,
            source=staging,
            statement_recorder=statement_recorder,
        )
        return
    target_exists: bool = adapter.relation_exists(
        connection,
        database=source_entry.database,
        schema=source_entry.schema,
        name=target_name,
    )
    if not target_exists:
        adapter.replace_table_from_relation(
            connection,
            target=target,
            source=staging,
            statement_recorder=statement_recorder,
        )
        return
    staging_sql: str = f"SELECT * FROM {staging}"
    if source_entry.write_strategy == SourceWriteStrategy.APPEND:
        adapter.append(
            connection,
            target=target,
            sql=staging_sql,
            statement_recorder=statement_recorder,
        )
        return
    if source_entry.write_strategy == SourceWriteStrategy.MERGE:
        adapter.merge(
            connection,
            target=target,
            sql=staging_sql,
            unique_key=source_entry.unique_key,
            statement_recorder=statement_recorder,
        )
        return
    raise ExecutorInputError(f"unsupported source write_strategy: {source_entry.write_strategy}")


def _load_current_cursor_value(
    *,
    adapter: BaseAdapter,
    connection: Any,
    source_entry: SourceEntry,
    target: str,
    target_name: str,
    statement_recorder: StatementRecorder,
) -> object | None:
    if source_entry.cursor_column is None:
        return None
    target_exists: bool = adapter.relation_exists(
        connection,
        database=source_entry.database,
        schema=source_entry.schema,
        name=target_name,
    )
    if not target_exists:
        return None
    sql: str = f"SELECT MAX({source_entry.cursor_column}) FROM {target}"
    statement_recorder.record(sql)
    cursor: Any = adapter.execute(connection, sql)
    row: object | None = cursor.fetchone()
    if row is None:
        return None
    return row[0]
