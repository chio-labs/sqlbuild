"""Source loader execution."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo, StatementRecorder
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.executor.load.helpers.cursors import (
    exclusive_cursor_end,
    format_cursor_bound,
    load_staging_cursor_bounds,
)
from sqlbuild.executor.load.helpers.external import execute_external_source_load
from sqlbuild.executor.load.helpers.relation_refs import (
    build_loader_relation_refs,
    build_source_relation_refs,
)
from sqlbuild.executor.load.helpers.schema import validate_and_evolve_existing_target
from sqlbuild.executor.load.helpers.staging import write_loader_rows_to_staging
from sqlbuild.executor.load.models import LoaderContext, LoadExecutionResult
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.helpers.load_execution import (
    is_untargeted_self_managed_intermediate,
    load_resource_kind,
)
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.shared.helpers.naming import resolve_qualified_name_parts
from sqlbuild.shared.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


def execute_source_load(
    *,
    source_entry: SourceEntry,
    loader_function: DiscoveredLoaderFunction,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    run_id: str,
    environment: str | None,
    vars: dict[str, object],
    is_reload: bool,
    start_cursor_ts: datetime | None = None,
    end_cursor_ts: datetime | None = None,
    start_cursor_int: int | None = None,
    end_cursor_int: int | None = None,
    statement_recorder: StatementRecorder,
    use_color: bool = False,
    loader_ref_entries: Mapping[Callable[..., object], SourceEntry] | None = None,
    source_ref_entries: Mapping[str, SourceEntry] | None = None,
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
        resource_kind: ExecutionResourceKind = load_resource_kind(source_entry)
        if loader_function.connection_mode == LoaderConnectionMode.EXTERNAL:
            return execute_external_source_load(
                source_entry=source_entry,
                loader_function=loader_function,
                adapter=adapter,
                connection_config=connection_config,
                target=target,
                target_name=target_name,
                run_id=run_id,
                environment=environment,
                vars=vars,
                is_reload=is_reload,
                start_cursor_ts=start_cursor_ts,
                end_cursor_ts=end_cursor_ts,
                start_cursor_int=start_cursor_int,
                end_cursor_int=end_cursor_int,
                statement_recorder=statement_recorder,
                use_color=use_color,
                resource_kind=resource_kind,
                start=start,
            )
        supported_write_strategies: frozenset[SourceWriteStrategy] = frozenset(
            {
                SourceWriteStrategy.APPEND,
                SourceWriteStrategy.DELETE_INSERT,
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
                "but sqb load currently supports only write_strategy append, delete_insert, "
                "merge, and table"
            )
        adapter.ensure_schema(
            connection,
            database=source_entry.database,
            schema=source_entry.schema,
            statement_recorder=statement_recorder,
        )
        context: LoaderContext = LoaderContext(
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            target=target,
            target_database=source_entry.database,
            target_schema=source_entry.schema,
            target_name=target_name,
            run_id=run_id,
            environment=environment,
            vars=vars,
            is_reload=is_reload,
            use_color=use_color,
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
            start_cursor_ts=start_cursor_ts,
            end_cursor_ts=end_cursor_ts,
            start_cursor_int=start_cursor_int,
            end_cursor_int=end_cursor_int,
            loader_refs=build_loader_relation_refs(
                adapter=adapter,
                connection=connection,
                entries=loader_ref_entries or {},
                statement_recorder=statement_recorder,
            ),
            source_refs=build_source_relation_refs(
                adapter=adapter,
                connection=connection,
                entries=source_ref_entries or {},
                statement_recorder=statement_recorder,
            ),
        )
        raw_rows: object = loader_function.function(context)
        if raw_rows is None:
            if is_untargeted_self_managed_intermediate(
                source_entry=source_entry,
                loader_function=loader_function,
            ):
                raise ExecutorInputError(
                    f"Loader '{loader_function.name}' returned no rows and has no target declared"
                )
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
                resource_kind=resource_kind,
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
            resource_kind=resource_kind,
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
        resource_kind=resource_kind,
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
    target_exists: bool = adapter.relation_exists(
        connection,
        database=source_entry.database,
        schema=source_entry.schema,
        name=target_name,
    )
    staging_columns: tuple[ColumnInfo, ...] = adapter.describe_relation(connection, staging)
    if target_exists:
        validate_and_evolve_existing_target(
            adapter=adapter,
            connection=connection,
            source_entry=source_entry,
            target=target,
            staging_columns=staging_columns,
            statement_recorder=statement_recorder,
        )
    if source_entry.write_strategy == SourceWriteStrategy.TABLE:
        adapter.replace_table_from_relation(
            connection,
            target=target,
            source=staging,
            statement_recorder=statement_recorder,
        )
        return
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
            columns=tuple(column.name for column in staging_columns),
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
    if source_entry.write_strategy == SourceWriteStrategy.DELETE_INSERT:
        if source_entry.cursor_column is None:
            raise ExecutorInputError(
                f"Source '{source_entry.name}' write_strategy delete_insert requires cursor_column"
            )
        cursor_bounds: tuple[object | None, object | None] = load_staging_cursor_bounds(
            adapter=adapter,
            connection=connection,
            staging=staging,
            cursor_column=source_entry.cursor_column,
            statement_recorder=statement_recorder,
        )
        cursor_start, cursor_max = cursor_bounds
        if cursor_start is None or cursor_max is None:
            return
        adapter.delete_insert_cursor(
            connection,
            target=target,
            sql=staging_sql,
            cursor_column=source_entry.cursor_column,
            cursor_start=format_cursor_bound(cursor_start),
            cursor_end=format_cursor_bound(exclusive_cursor_end(cursor_max)),
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
    sql: str = f"SELECT MAX({adapter.render_identifier(source_entry.cursor_column)}) FROM {target}"
    statement_recorder.record(sql)
    cursor: Any = adapter.execute(connection, sql)
    row: object | None = cursor.fetchone()
    if row is None:
        return None
    return row[0]
