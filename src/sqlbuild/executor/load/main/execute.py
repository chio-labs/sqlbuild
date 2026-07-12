"""Source loader execution."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.models import ColumnInfo
from sqlbuild.adapter.relation_naming.main.resolve_qualified_name_parts import (
    resolve_qualified_name_parts,
)
from sqlbuild.compiler.discovery.models import DiscoveredLoaderFunction
from sqlbuild.compiler.discovery.types import LoaderConnectionMode
from sqlbuild.executor.exceptions import ExecutorInputError
from sqlbuild.executor.helpers.load_execution import load_resource_kind
from sqlbuild.executor.load.helpers.cursors import (
    exclusive_cursor_end,
    format_cursor_bound,
    load_staging_cursor_bounds,
)
from sqlbuild.executor.load.helpers.external import execute_external_source_load
from sqlbuild.executor.load.helpers.loader_invocation import (
    build_loader_context,
    interpret_loader_return,
    validate_source_write_strategy,
)
from sqlbuild.executor.load.helpers.schema import validate_and_evolve_existing_target
from sqlbuild.executor.load.helpers.staging import write_loader_rows_to_staging
from sqlbuild.executor.load.models import (
    LoaderContext,
    LoaderDestination,
    LoaderRefBindings,
    LoadExecutionResult,
    LoadRuntimeParams,
)
from sqlbuild.executor.types import ExecutionStatus
from sqlbuild.provider.main.runtime import invoke_with_providers
from sqlbuild.runtime.contracts.types import ExecutionResourceKind
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


def execute_source_load(
    *,
    source_entry: SourceEntry,
    loader_function: DiscoveredLoaderFunction,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    connection: Any,
    runtime: LoadRuntimeParams,
    statement_recorder: StatementRecorder,
    loader_ref_entries: Mapping[Callable[..., object], SourceEntry] | None = None,
    source_ref_entries: Mapping[str, SourceEntry] | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> LoadExecutionResult:
    """Run one source loader and write returned rows using the table strategy."""

    destination_name: str = (
        source_entry.table if source_entry.table is not None else source_entry.name
    )
    destination_relation: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=source_entry.database,
        schema=source_entry.schema,
        name=destination_name,
    )
    staging: str = resolve_qualified_name_parts(
        adapter=adapter,
        database=source_entry.database,
        schema=source_entry.schema,
        name=f"{destination_name}__staging",
    )
    destination: LoaderDestination = LoaderDestination(
        relation=destination_relation, name=destination_name
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
                destination=destination,
                runtime=runtime,
                statement_recorder=statement_recorder,
                resource_kind=resource_kind,
                start=start,
                on_progress=on_progress,
            )
        validate_source_write_strategy(source_entry)
        adapter.ensure_schema(
            connection=connection,
            database=source_entry.database,
            schema=source_entry.schema,
            statement_recorder=statement_recorder,
        )
        context: LoaderContext = build_loader_context(
            source_entry=source_entry,
            loader_function=loader_function,
            adapter=adapter,
            connection_config=connection_config,
            connection=connection,
            destination=destination,
            runtime=runtime,
            statement_recorder=statement_recorder,
            ref_bindings=LoaderRefBindings(
                loader_ref_entries=loader_ref_entries,
                source_ref_entries=source_ref_entries,
            ),
            on_progress=on_progress,
        )
        raw_rows: object = invoke_with_providers(
            function=loader_function.function,
            context=context,
            providers=runtime.providers,
        )
        early_result: LoadExecutionResult | None = interpret_loader_return(
            raw_rows=raw_rows,
            source_entry=source_entry,
            loader_function=loader_function,
            destination_relation=destination_relation,
            resource_kind=resource_kind,
            statement_recorder=statement_recorder,
            start=start,
        )
        if early_result is not None:
            return early_result
        rows_loaded: int = write_loader_rows_to_staging(
            loader_return_value=raw_rows,
            source_entry=source_entry,
            adapter=adapter,
            connection=connection,
            staging=staging,
            statement_recorder=statement_recorder,
        )
        adapter = _apply_source_write_strategy(
            adapter=adapter,
            connection=connection,
            source_entry=source_entry,
            target=destination_relation,
            target_name=destination_name,
            staging=staging,
            statement_recorder=statement_recorder,
        )
        adapter.drop(
            connection=connection,
            destination=staging,
            if_exists=True,
            statement_recorder=statement_recorder,
        )
    except Exception as error:
        try:
            adapter.drop(
                connection=connection,
                destination=staging,
                if_exists=True,
                statement_recorder=statement_recorder,
            )
        except Exception:
            pass
        return LoadExecutionResult(
            source_name=source_entry.name,
            loader_name=loader_function.name,
            status=ExecutionStatus.FAILED,
            target=destination_relation,
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
        target=destination_relation,
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
) -> BaseAdapter:
    target_exists: bool = adapter.relation_exists(
        connection=connection,
        database=source_entry.database,
        schema=source_entry.schema,
        name=target_name,
    )
    staging_columns: tuple[ColumnInfo, ...] = adapter.describe_relation(
        connection=connection, relation=staging
    )
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
            connection=connection,
            destination=target,
            origin=staging,
            statement_recorder=statement_recorder,
        )
        return adapter
    if not target_exists:
        adapter.replace_table_from_relation(
            connection=connection,
            destination=target,
            origin=staging,
            statement_recorder=statement_recorder,
        )
        return adapter
    staging_sql: str = f"SELECT * FROM {staging}"
    if source_entry.write_strategy == SourceWriteStrategy.APPEND:
        adapter.append(
            connection=connection,
            destination=target,
            sql=staging_sql,
            columns=tuple(column.name for column in staging_columns),
            statement_recorder=statement_recorder,
        )
        return adapter
    if source_entry.write_strategy == SourceWriteStrategy.MERGE:
        adapter.merge(
            connection=connection,
            destination=target,
            sql=staging_sql,
            unique_key=source_entry.unique_key,
            statement_recorder=statement_recorder,
        )
        return adapter
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
            return adapter
        adapter.delete_insert_cursor(
            connection=connection,
            destination=target,
            sql=staging_sql,
            cursor_column=source_entry.cursor_column,
            cursor_start=format_cursor_bound(cursor_start),
            cursor_end=format_cursor_bound(exclusive_cursor_end(cursor_max)),
            statement_recorder=statement_recorder,
        )
        return adapter
    raise ExecutorInputError(f"unsupported source write_strategy: {source_entry.write_strategy}")
